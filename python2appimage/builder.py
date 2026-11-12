"""AppImage assembly: the build pipeline and top-level run()."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Sequence

from .config import Config
from .constants import COPY_IGNORE, PIP_STRIPPED_VARS, PROG, SUPPORTED_ARCHES
from .download import obtain_appimagetool, obtain_python_runtime
from .errors import Error
from .fsutils import human_size, is_inside, make_world_readable
from .icons import detect_icon, write_placeholder_icon
from .logger import log
from .project import Project, detect_project, resolve_output
from .templates import render_apprun, rewrite_desktop_entry


def pip_environment() -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in PIP_STRIPPED_VARS}
    env.update(PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_CACHE_DIR="1",
               PIP_REQUIRE_VIRTUALENV="0", PIP_USER="0", PYTHONNOUSERSITE="1")
    return env


class AppImageBuilder:

    def __init__(self, config: Config, project: Project, arch: str, output: Path):
        self.config = config
        self.project = project
        self.arch = arch
        self.output = output
        self.work_dir = Path()
        self.appdir = Path()

    @property
    def python(self) -> Path:
        return self.appdir / "usr" / "bin" / f"python{self.config.python_version}"

    @property
    def source_dir(self) -> Path:
        return self.appdir / "usr" / "app"

    def build(self) -> None:
        runtime = obtain_python_runtime(self.config.python_version, self.arch)
        tool = obtain_appimagetool(self.arch)

        with tempfile.TemporaryDirectory(prefix=f"{PROG}-") as tmp:
            self.work_dir = Path(tmp)
            self.appdir = self.work_dir / "AppDir"

            self.extract_runtime(runtime)
            self.strip_runtime_metadata()
            self.copy_sources()
            self.install_dependencies()
            self.remove_build_leftovers()
            self.compile_bytecode()
            self.install_icon()
            self.write_desktop_file()
            self.write_apprun()
            self.package(tool)

        log.info(f"done: {self.output} ({human_size(self.output.stat().st_size)})")

    def extract_runtime(self, runtime: Path) -> None:
        log.info("extracting Python runtime")
        if not os.access(runtime, os.X_OK):
            local = self.work_dir / "runtime.AppImage"
            shutil.copyfile(runtime, local)
            local.chmod(0o755)
            runtime = local
        env = {**os.environ, "APPIMAGE_EXTRACT_AND_RUN": "1"}
        self._run([str(runtime), "--appimage-extract"], "extracting the runtime",
                  cwd=self.work_dir, env=env, stdout=subprocess.DEVNULL)
        (self.work_dir / "squashfs-root").rename(self.appdir)
        if not os.access(self.python, os.X_OK):
            raise Error("Python interpreter missing from runtime: "
                        f"usr/bin/python{self.config.python_version}")

    def strip_runtime_metadata(self) -> None:
        for pattern in ("*.desktop", "AppRun", "python*.png", "python*.svg"):
            for path in self.appdir.glob(pattern):
                path.unlink()
        (self.appdir / ".DirIcon").unlink(missing_ok=True)
        for name in ("applications", "metainfo"):
            shutil.rmtree(self.appdir / "usr" / "share" / name, ignore_errors=True)
        for path in self.appdir.glob("usr/share/icons/hicolor/*/apps/python*"):
            path.unlink()

    def copy_sources(self) -> None:
        log.info("copying project sources")
        shutil.copytree(self.project.directory, self.source_dir, symlinks=True,
                        ignore=shutil.ignore_patterns(*COPY_IGNORE))

    def install_dependencies(self) -> None:
        project = self.project
        command = [str(self.python), "-m", "pip", "install", "--no-warn-script-location"]
        if log.quiet:
            command.append("--quiet")

        if project.requirements:
            log.info("installing dependencies from requirements.txt")
            command += ["-r", project.requirements.name]
        elif project.installable:
            log.info("installing the project and its dependencies")
            command.append(".")
        else:
            log.warn("no requirements.txt or pyproject.toml found; "
                     "continuing without extra dependencies")
            return
        self._run(command, "pip", cwd=self.source_dir, env=pip_environment(),
                  stdout=sys.stderr)

    def remove_build_leftovers(self) -> None:
        leftovers = [self.source_dir / "build"]
        leftovers += self.source_dir.glob("*.egg-info")
        leftovers += self.source_dir.glob("src/*.egg-info")
        for path in leftovers:
            shutil.rmtree(path, ignore_errors=True)

    def _purelib(self) -> Optional[Path]:
        code = "import sysconfig; print(sysconfig.get_paths()['purelib'])"
        result = subprocess.run([str(self.python), "-c", code], env=pip_environment(),
                                text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        if result.returncode:
            return None
        path = Path(result.stdout.strip())
        return path if path.is_dir() and is_inside(self.appdir, path) else None

    def compile_bytecode(self) -> None:
        if not self.config.compile_bytecode:
            return
        log.info("precompiling bytecode")

        command = [str(self.python), "-m", "compileall", "-q"]
        if int(self.config.python_version.split(".")[1]) >= 7:
            # the AppImage is read-only, so sources can never change under the cache
            command += ["--invalidation-mode", "unchecked-hash"]

        # force the project's own files; leave pip's existing .pyc files alone
        targets = [(self.source_dir, ["-f"]), (self._purelib(), [])]
        for path, extra in targets:
            if path is None:
                continue
            result = subprocess.run(command + extra + [str(path)], env=pip_environment())
            if result.returncode:
                log.warn(f"some files in {path.name} could not be compiled; "
                         "they will still run, just without cached bytecode")

    def install_icon(self) -> None:
        project = self.project
        icon = self.config.icon
        if icon:
            log.info(f"icon (given): {icon}")
        else:
            icon = detect_icon(project)
            if icon:
                log.info(f"icon (detected): {icon.relative_to(project.directory)}")

        if not icon:
            log.warn("no icon found; using a placeholder (set one with --icon=FILE)")
            icon = self.work_dir / "placeholder.png"
            write_placeholder_icon(icon)

        extension = icon.suffix.lower()
        size_dir = "scalable" if extension == ".svg" else "256x256"
        theme_dir = self.appdir / "usr" / "share" / "icons" / "hicolor" / size_dir / "apps"
        theme_dir.mkdir(parents=True, exist_ok=True)

        shutil.copyfile(icon, self.appdir / f"{project.app_name}{extension}")
        shutil.copyfile(icon, self.appdir / ".DirIcon")
        shutil.copyfile(icon, theme_dir / f"{project.app_name}{extension}")

    def write_desktop_file(self) -> None:
        project = self.project
        if project.desktop_file:
            log.info("adjusting desktop file: "
                     f"{project.desktop_file.relative_to(project.directory)}")
            text = project.desktop_file.read_text(encoding="utf-8", errors="replace")
        else:
            log.info("no desktop file found; generating one")
            text = "[Desktop Entry]\n"

        content = rewrite_desktop_entry(text, project.app_name, project.display_name,
                                        self.config.app_type == "cli")
        (self.appdir / f"{project.app_name}.desktop").write_text(content, encoding="utf-8")
        applications = self.appdir / "usr" / "share" / "applications"
        applications.mkdir(parents=True, exist_ok=True)
        (applications / f"{project.app_name}.desktop").write_text(content, encoding="utf-8")

    def write_apprun(self) -> None:
        apprun = self.appdir / "AppRun"
        apprun.write_text(
            render_apprun(self.project, self.config.python_version, self.config.app_type),
            encoding="utf-8",
        )
        apprun.chmod(0o755)

    def package(self, tool: Path) -> None:
        log.info("building AppImage")
        make_world_readable(self.appdir)
        self.output.unlink(missing_ok=True)

        command = [str(tool), "--no-appstream", str(self.appdir), str(self.output)]
        env = {**os.environ, "ARCH": self.arch, "APPIMAGE_EXTRACT_AND_RUN": "1"}
        if log.quiet:
            result = subprocess.run(command, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode:
                sys.stderr.write(result.stdout)
                raise Error("appimagetool failed")
        else:
            self._run(command, "appimagetool", env=env, stdout=sys.stderr)
        self.output.chmod(self.output.stat().st_mode | 0o111)

    @staticmethod
    def _run(command: Sequence[str], what: str, **kwargs) -> None:
        try:
            subprocess.run(command, check=True, **kwargs)
        except subprocess.CalledProcessError as exc:
            raise Error(f"{what} failed (exit status {exc.returncode})") from exc
        except OSError as exc:
            raise Error(f"{what} failed: {exc}") from exc


def detect_arch() -> str:
    if not sys.platform.startswith("linux"):
        raise Error("AppImages can only be built on Linux")
    machine = platform.machine()
    if machine not in SUPPORTED_ARCHES:
        raise Error(f"unsupported architecture: {machine} "
                    f"(need {' or '.join(SUPPORTED_ARCHES)})")
    return machine


def run(config: Config) -> None:
    arch = detect_arch()
    project = detect_project(config.directory, config.entry)
    output = resolve_output(config.output, project, arch)

    version = f" v{project.version}" if project.version else ""
    log.info(f"project:     {project.directory}")
    log.info(f"application: {project.app_name} ({project.display_name}){version}")
    log.info(f"type:        {config.app_type}")
    log.info(f"entry point: {project.entry.describe()}")
    log.info(f"output:      {output}")

    AppImageBuilder(config, project, arch, output).build()
