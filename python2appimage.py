#!/usr/bin/env python3
from __future__ import annotations

import argparse
import dataclasses
import http.client
import json
import os
import platform
import re
import shlex
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import textwrap
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

if sys.version_info < (3, 8):
    sys.exit("python2appimage: Python 3.8 or newer is required")


VERSION = "1.0.0"
AUTHOR = "hyunazmi"
REPO_URL = "https://github.com/hyunazmi/python2appimage"
PROG = "python2appimage"

DEFAULT_PYTHON_VERSION = "3.11"
DEFAULT_TYPE = "gui"
APP_TYPES = ("gui", "cli")
SUPPORTED_ARCHES = ("x86_64", "aarch64")
ICON_EXTENSIONS = (".png", ".svg", ".xpm")
ICON_DIR_NAMES = ("assets", "icons", "icon", "resources", "images")
NON_APP_DIRS = frozenset({"tests", "test", "docs", "examples", "scripts"})
IGNORED_SCRIPTS = frozenset({"setup.py", "conftest.py", "noxfile.py", "fabfile.py"})
PRUNE_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
)
COPY_IGNORE = tuple(sorted(PRUNE_DIRS | {".github"})) + ("*.pyc", "*.AppImage", "*.zip")
PIP_STRIPPED_VARS = ("PYTHONHOME", "PYTHONPATH", "PIP_TARGET", "PIP_PREFIX",
                     "PIP_ROOT", "PIP_USER")

PYTHON_RELEASES_URL = "https://github.com/niess/python-appimage/releases"
APPIMAGETOOL_URL = (
    "https://github.com/AppImage/appimagetool/releases/download/continuous"
)
MAX_PAGE_BYTES = 10_000_000
HELP_WIDTH = 79

DOTTED_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")
DIR_VERSION = re.compile(r"(?P<name>.+)-v?(?P<version>\d+(?:\.\d+)*)")
TOML_SECTION = re.compile(r"^\s*\[\s*([^\[\]]+?)\s*\]\s*(?:#.*)?$")
TOML_STRING_PAIR = re.compile(
    r"""^\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z0-9_.-]+))\s*=\s*"""
    r"""(?:"([^"]*)"|'([^']*)')\s*(?:#.*)?$"""
)

APPRUN_HEAD = """\
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export APPDIR="$HERE"
unset PYTHONHOME PYTHONSTARTUP VIRTUAL_ENV
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=@PYTHONPATH@
"""

APPRUN_TERMINAL = r"""SELF="${APPIMAGE:-$0}"
if [ ! -t 0 ] && [ ! -t 1 ] && [ ! -t 2 ] && [ -z "$@GUARD@" ] \
        && { [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; }; then
    export @GUARD@=1
    RUN='"$0" "$@"; status=$?; printf "\n[process exited with status %s, press Enter to close] " "$status"; read -r _; exit "$status"'
    for terminal in x-terminal-emulator gnome-terminal konsole xfce4-terminal mate-terminal lxterminal alacritty kitty xterm; do
        command -v "$terminal" >/dev/null 2>&1 || continue
        case "$terminal" in
            gnome-terminal) exec "$terminal" --wait -- bash -c "$RUN" "$SELF" "$@" ;;
            xfce4-terminal|mate-terminal) exec "$terminal" -x bash -c "$RUN" "$SELF" "$@" ;;
            kitty) exec "$terminal" bash -c "$RUN" "$SELF" "$@" ;;
            *) exec "$terminal" -e bash -c "$RUN" "$SELF" "$@" ;;
        esac
    done
    echo "@PROG@: no terminal emulator found, running without one" >&2
fi
"""


class Error(Exception):
    pass


class UsageError(Exception):
    pass


class Logger:

    def __init__(self) -> None:
        self.quiet = False

    def info(self, message: str) -> None:
        if not self.quiet:
            print(f"{PROG}: {message}", file=sys.stderr)

    def warn(self, message: str) -> None:
        print(f"{PROG}: warning: {message}", file=sys.stderr)


log = Logger()


@dataclasses.dataclass(frozen=True)
class Option:
    short: str
    long: str
    help: str
    action: str = "store"
    metavar: str = ""
    dest: str = ""
    default: Optional[str] = None


OPTIONS: Tuple[Option, ...] = (
    Option("-d", "--directory", "project directory (default: current directory)",
           metavar="DIR", dest="directory", default="."),
    Option("-e", "--entry", "what to run: MODULE, MODULE:FUNCTION or SCRIPT.py "
           "(default: auto-detected)", metavar="ENTRY", dest="entry"),
    Option("-t", "--type", f"application type: {' or '.join(APP_TYPES)} "
           f"(default: {DEFAULT_TYPE})", metavar="TYPE", dest="app_type",
           default=DEFAULT_TYPE),
    Option("-i", "--icon", "application icon (default: auto-detected)",
           metavar="FILE", dest="icon"),
    Option("-o", "--output", "output file (default: NAME-VERSION-ARCH.AppImage)",
           metavar="FILE", dest="output"),
    Option("-p", "--python-version", "bundled Python version "
           f"(default: {DEFAULT_PYTHON_VERSION})",
           metavar="VER", dest="python_version", default=DEFAULT_PYTHON_VERSION),
    Option("-q", "--quiet", "suppress progress messages",
           action="store_true", dest="quiet"),
    Option("-h", "--help", "display this help and exit", action="help"),
    Option("-V", "--version", "output version information and exit",
           action="version"),
)


def render_help() -> str:
    labels = [
        f"{o.short}, {o.long}" + (f"={o.metavar}" if o.metavar else "")
        for o in OPTIONS
    ]
    pad = max(len(label) for label in labels)
    indent = 2 + pad + 2

    rows: List[str] = []
    for label, option in zip(labels, OPTIONS):
        lines = textwrap.wrap(option.help, HELP_WIDTH - indent,
                              break_on_hyphens=False) or [""]
        rows.append(f"  {label.ljust(pad)}  {lines[0]}")
        rows.extend(" " * indent + line for line in lines[1:])

    return "\n".join([
        f"Usage: {PROG} [OPTION]...",
        "Build an AppImage from a Python project.",
        "",
        f"Author: {AUTHOR}",
        f"GitHub: {REPO_URL}",
        "",
        "Options:",
        *rows,
    ])


def render_version() -> str:
    return "\n".join([
        f"{PROG} {VERSION}",
        f"Copyright (C) 2026 {AUTHOR}",
        "License MIT: <https://opensource.org/licenses/MIT>.",
        "This is free software: you are free to change and redistribute it.",
        "There is NO WARRANTY, to the extent permitted by law.",
        "",
        f"Written by {AUTHOR}.",
    ])


class _HelpAction(argparse.Action):
    def __init__(self, option_strings, dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings, dest=dest, default=default,
                         nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        print(render_help())
        parser.exit(0)


class _VersionAction(_HelpAction):
    def __call__(self, parser, namespace, values, option_string=None):
        print(render_version())
        parser.exit(0)


class _Parser(argparse.ArgumentParser):

    def error(self, message: str) -> None:
        match = re.match(r"argument (\S+): expected one argument", message)
        if match:
            option = match.group(1).split("/")[0]
            message = f"option '{option}' requires an argument"
        raise UsageError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog=PROG, add_help=False)
    for option in OPTIONS:
        flags = (option.short, option.long)
        if option.action == "store":
            parser.add_argument(*flags, dest=option.dest,
                                metavar=option.metavar, default=option.default)
        elif option.action == "store_true":
            parser.add_argument(*flags, dest=option.dest, action="store_true")
        elif option.action == "help":
            parser.add_argument(*flags, action=_HelpAction)
        else:
            parser.add_argument(*flags, action=_VersionAction)
    return parser


@dataclasses.dataclass(frozen=True)
class Config:
    directory: Path
    entry: Optional[str]
    app_type: str
    icon: Optional[Path]
    output: Optional[str]
    python_version: str
    quiet: bool


def parse_args(argv: Sequence[str]) -> Config:
    args, extras = build_parser().parse_known_args(argv)
    if extras:
        bad = extras[0]
        if bad.startswith("-"):
            raise UsageError(f"unrecognized option '{bad}'")
        raise UsageError(f"extra operand '{bad}'")

    if args.app_type not in APP_TYPES:
        valid = ", ".join(f"'{t}'" for t in APP_TYPES)
        raise UsageError(f"invalid argument '{args.app_type}' for '--type'\n"
                         f"Valid arguments are: {valid}")

    directory = Path(args.directory).expanduser()
    if not directory.is_dir():
        raise Error(f"cannot access '{args.directory}': no such directory")

    if not re.fullmatch(r"3\.\d+", args.python_version):
        raise Error(f"invalid Python version '{args.python_version}' "
                    "(expected 3.X, e.g. 3.11)")

    icon: Optional[Path] = None
    if args.icon:
        icon = Path(args.icon).expanduser()
        if not icon.is_file():
            raise Error(f"cannot access '{args.icon}': no such file")
        if icon.suffix.lower() not in ICON_EXTENSIONS:
            raise Error(f"unsupported icon format '{args.icon}' "
                        "(need .png, .svg or .xpm)")
        icon = icon.resolve()

    return Config(directory=directory.resolve(), entry=args.entry or None,
                  app_type=args.app_type, icon=icon, output=args.output,
                  python_version=args.python_version, quiet=args.quiet)


@dataclasses.dataclass(frozen=True)
class Entry:
    kind: str
    target: str

    def describe(self) -> str:
        if self.kind == "module":
            return f"python -m {self.target}"
        if self.kind == "callable":
            return f"call {self.target}"
        return f"python {self.target}"


@dataclasses.dataclass(frozen=True)
class PyProject:
    name: str = ""
    version: str = ""
    scripts: Dict[str, str] = dataclasses.field(default_factory=dict)
    installable: bool = False


@dataclasses.dataclass(frozen=True)
class Project:
    directory: Path
    app_name: str
    display_name: str
    version: str
    desktop_file: Optional[Path]
    desktop_icon: str
    entry: Entry
    requirements: Optional[Path]
    installable: bool
    has_src_dir: bool


def is_dotted_name(text: str) -> bool:
    return DOTTED_NAME.fullmatch(text) is not None


def is_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError, RuntimeError):
        return False
    return True


def iter_files(root: Path, max_depth: Optional[int] = None) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in PRUNE_DIRS)
        depth = len(Path(dirpath).relative_to(root).parts) + 1
        if max_depth is not None and depth >= max_depth:
            dirnames[:] = []
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_symlink() and not is_inside(root, path):
                continue
            yield path


def read_desktop_value(path: Path, key: str) -> str:
    in_entry = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("["):
            in_entry = line == "[Desktop Entry]"
        elif in_entry and line.startswith(key + "="):
            return line[len(key) + 1:]
    return ""


def read_pyproject(root: Path) -> PyProject:
    path = root / "pyproject.toml"
    if not path.is_file() or not is_inside(root, path):
        return PyProject()

    section = ""
    name = version = ""
    scripts: Dict[str, str] = {}
    installable = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lstrip().startswith("["):
            match = TOML_SECTION.match(line)
            section = match.group(1).strip() if match else "?"
            installable = installable or section in ("project", "build-system")
            continue
        pair = TOML_STRING_PAIR.match(line)
        if not pair:
            continue
        key = pair.group(1) or pair.group(2) or pair.group(3)
        value = pair.group(4) if pair.group(4) is not None else pair.group(5)
        if section == "project" and key == "name":
            name = value
        elif section == "project" and key == "version":
            version = value
        elif section == "project.scripts":
            scripts[key] = value
    return PyProject(name, version, scripts, installable)


def sanitize_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", text).strip("-.")


def sanitize_version(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+~-]", "-", text).strip("-.")


def parse_entry_spec(spec: str, root: Path) -> Entry:
    if ":" in spec:
        module, _, attr = spec.partition(":")
        if not (is_dotted_name(module) and is_dotted_name(attr)):
            raise Error(f"invalid entry '{spec}' (expected MODULE:FUNCTION)")
        return Entry("callable", f"{module}:{attr}")

    if spec.lower().endswith(".py") or "/" in spec:
        script = root / spec
        if not script.is_file() or not is_inside(root, script):
            raise Error(f"entry script not found in the project: {spec}")
        return Entry("script", script.resolve().relative_to(root).as_posix())

    if not is_dotted_name(spec):
        raise Error(f"invalid entry '{spec}' "
                    "(expected MODULE, MODULE:FUNCTION or SCRIPT.py)")
    return Entry("module", spec)


def entry_from_scripts(scripts: Dict[str, str], app_name: str) -> Optional[Entry]:
    valid: Dict[str, str] = {}
    for key, value in scripts.items():
        target = value.split("[", 1)[0].strip()
        module, separator, attr = target.partition(":")
        if separator and is_dotted_name(module) and is_dotted_name(attr):
            valid[key] = target
    if not valid:
        return None
    preferred = next((key for key in valid if sanitize_name(key) == app_name), None)
    return Entry("callable", valid[preferred or next(iter(valid))])


def find_main_module(root: Path, app_name: str) -> Optional[Entry]:
    wanted = app_name.replace("-", "_").lower()
    packages: List[str] = []
    for path in iter_files(root, 3):
        if path.name != "__main__.py":
            continue
        parts = path.relative_to(root).parts
        if len(parts) == 2:
            package = parts[0]
        elif len(parts) == 3 and parts[0] == "src":
            package = parts[1]
        else:
            continue
        if package not in NON_APP_DIRS and is_dotted_name(package) and "." not in package:
            packages.append(package)
    if not packages:
        return None
    match = next((p for p in packages if p.lower() == wanted), None)
    return Entry("module", match or packages[0])


def find_script(root: Path, app_name: str) -> Optional[Entry]:
    wanted = app_name.replace("-", "_")
    for name in ("__main__.py", f"{app_name}.py", f"{wanted}.py", "main.py", "app.py"):
        path = root / name
        if path.is_file() and is_inside(root, path):
            return Entry("script", name)

    scripts = sorted(
        p.name for p in root.glob("*.py")
        if p.is_file() and is_inside(root, p)
        and p.name not in IGNORED_SCRIPTS and not p.name.startswith("test_")
    )
    return Entry("script", scripts[0]) if len(scripts) == 1 else None


def detect_entry(root: Path, app_name: str, pyproject: PyProject,
                 spec: Optional[str]) -> Entry:
    if spec:
        return parse_entry_spec(spec, root)
    entry = (entry_from_scripts(pyproject.scripts, app_name)
             or find_main_module(root, app_name)
             or find_script(root, app_name))
    if entry is None:
        raise Error(f"no entry point found in '{root}'; "
                    "use --entry=MODULE, MODULE:FUNCTION or SCRIPT.py")
    return entry


def detect_project(root: Path, entry_spec: Optional[str]) -> Project:
    desktop = next((p for p in iter_files(root, 2) if p.suffix == ".desktop"), None)
    pyproject = read_pyproject(root)

    match = DIR_VERSION.fullmatch(root.name)
    dir_name = match["name"] if match else root.name
    dir_version = match["version"] if match else ""

    raw_name = desktop.stem if desktop else (pyproject.name or dir_name)
    app_name = sanitize_name(raw_name) or sanitize_name(dir_name)
    if not app_name:
        raise Error("cannot determine the application name")

    display_name = ""
    if desktop:
        display_name = read_desktop_value(desktop, "Name")
    display_name = display_name or pyproject.name or app_name

    requirements = root / "requirements.txt"
    has_requirements = requirements.is_file() and is_inside(root, requirements)
    installable = (pyproject.installable or (root / "setup.py").is_file()
                   or (root / "setup.cfg").is_file())

    return Project(
        directory=root,
        app_name=app_name,
        display_name=display_name,
        version=sanitize_version(pyproject.version or dir_version),
        desktop_file=desktop,
        desktop_icon=read_desktop_value(desktop, "Icon") if desktop else "",
        entry=detect_entry(root, app_name, pyproject, entry_spec),
        requirements=requirements if has_requirements else None,
        installable=installable,
        has_src_dir=(root / "src").is_dir(),
    )


def resolve_output(requested: Optional[str], project: Project, arch: str) -> Path:
    suffix = f"-{project.version}" if project.version else ""
    default_name = f"{project.app_name}{suffix}-{arch}.AppImage"

    if not requested:
        output = Path(default_name)
    else:
        path = Path(requested).expanduser()
        if requested.endswith("/") or path.is_dir():
            output = path / default_name
        elif requested.endswith(".AppImage"):
            output = path
        else:
            output = path.with_name(path.name + ".AppImage")

    output = output.resolve()
    if output.is_dir():
        raise Error(f"'{output}' is a directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _largest(paths: Iterable[Path]) -> Optional[Path]:
    best: Optional[Path] = None
    best_size = 0
    for path in paths:
        try:
            size = path.stat().st_size if path.is_file() else 0
        except OSError:
            size = 0
        if size > best_size:
            best, best_size = path, size
    return best


def _images(root: Path) -> Iterator[Path]:
    return (p for p in iter_files(root) if p.suffix.lower() in ICON_EXTENSIONS)


def _find_icon_by_name(root: Path, name: str) -> Optional[Path]:
    return _largest(p for p in _images(root) if p.stem.lower() == name.lower())


def detect_icon(project: Project) -> Optional[Path]:
    root = project.directory

    icon = project.desktop_icon
    if icon:
        candidate = Path(icon)
        if candidate.is_absolute():
            if (candidate.suffix.lower() in ICON_EXTENSIONS and candidate.is_file()
                    and is_inside(root, candidate)):
                return candidate
        else:
            name = candidate.name
            if candidate.suffix.lower() in ICON_EXTENSIONS:
                name = candidate.stem
            found = _find_icon_by_name(root, name)
            if found:
                return found

    for name in (project.app_name, project.app_name.replace("-", "_"), "icon", "logo"):
        found = _find_icon_by_name(root, name)
        if found:
            return found

    found = _largest(
        p for p in _images(root)
        if any(part.lower() in ICON_DIR_NAMES
               for part in p.relative_to(root).parts[:-1])
    )
    if found:
        return found

    return _largest(p for p in _images(root) if p.suffix.lower() == ".png")


def write_placeholder_icon(dest: Path, size: int = 256) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = struct.pack(">I", len(data)) + tag + data
        return body + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    row = b"\x00" + bytes((52, 120, 246, 255)) * size
    dest.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * size))
        + chunk(b"IEND", b"")
    )


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    path = Path(base) / PROG
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _open_url(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": f"{PROG}/{VERSION}"})
    try:
        return urllib.request.urlopen(request, timeout=60)
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise Error(f"cannot download {url}: {exc}") from exc


def fetch_text(url: str) -> str:
    try:
        with _open_url(url) as response:
            return response.read(MAX_PAGE_BYTES).decode("utf-8", errors="replace")
    except (OSError, http.client.HTTPException) as exc:
        raise Error(f"cannot download {url}: {exc}") from exc


def download(url: str, dest: Path) -> None:
    part = dest.with_name(dest.name + ".part")
    show_progress = not log.quiet and sys.stderr.isatty()
    try:
        with _open_url(url) as response, part.open("wb") as out:
            header = response.headers.get("Content-Length", "")
            total = int(header) if header.isdigit() else 0
            done = 0
            while True:
                block = response.read(1 << 16)
                if not block:
                    break
                out.write(block)
                done += len(block)
                if show_progress and total:
                    print(f"\r{PROG}: {done * 100 // total:3d}% of "
                          f"{total / 1e6:.1f} MB", end="", file=sys.stderr)
        if show_progress:
            print(file=sys.stderr)
        if total and done != total:
            raise Error(f"incomplete download: {url}")
        part.replace(dest)
    except (OSError, http.client.HTTPException) as exc:
        raise Error(f"cannot download {url}: {exc}") from exc
    finally:
        part.unlink(missing_ok=True)


def locate_python_runtime(py_version: str, arch: str) -> str:
    nodot = py_version.replace(".", "")
    html = fetch_text(f"{PYTHON_RELEASES_URL}/expanded_assets/python{py_version}")
    pattern = re.compile(
        rf'href="(/[^"]*/python(?P<ver>[0-9]+(?:\.[0-9]+)*)-cp{nodot}-cp{nodot}'
        rf'-manylinux[^/"]*_{arch}\.AppImage)"'
    )
    found = [(tuple(int(n) for n in m["ver"].split(".")), m.group(1))
             for m in pattern.finditer(html)]
    if not found:
        raise Error(f"no Python {py_version} runtime for {arch} found "
                    "in python-appimage releases")

    newest = max(version for version, _ in found)
    candidates = sorted(path for version, path in found if version == newest)
    pick = next((p for p in candidates if "manylinux2014" in p), candidates[0])
    return "https://github.com" + pick


def obtain_python_runtime(py_version: str, arch: str) -> Path:
    override = os.environ.get("PYTHON_APPIMAGE")
    if override:
        path = Path(override)
        if not path.is_file():
            raise Error(f"PYTHON_APPIMAGE: no such file: {override}")
        return path

    url = locate_python_runtime(py_version, arch)
    path = cache_dir() / url.rsplit("/", 1)[1]
    if path.is_file() and path.stat().st_size > 0:
        log.info(f"using cached Python runtime: {path.name}")
    else:
        log.info(f"downloading Python runtime: {path.name}")
        download(url, path)
        path.chmod(0o755)
    return path


def obtain_appimagetool(arch: str) -> Path:
    override = os.environ.get("APPIMAGETOOL")
    if override:
        path = Path(override)
        if not os.access(path, os.X_OK):
            raise Error(f"APPIMAGETOOL: not executable: {override}")
        return path

    path = cache_dir() / f"appimagetool-{arch}.AppImage"
    if os.access(path, os.X_OK):
        log.info("using cached appimagetool")
    else:
        log.info("downloading appimagetool")
        download(f"{APPIMAGETOOL_URL}/appimagetool-{arch}.AppImage", path)
        path.chmod(0o755)
    return path


def rewrite_desktop_entry(text: str, app_name: str, display_name: str,
                          terminal: bool) -> str:
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == "[Desktop Entry]"), None)
    if start is None:
        lines.insert(0, "[Desktop Entry]")
        start = 0
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("[")), len(lines))

    entry: List[str] = []
    for line in lines[start + 1:end]:
        key = line.split("=", 1)[0]
        if key in ("TryExec", "Path", "Terminal"):
            continue
        if key == "Exec":
            line = f"Exec={app_name}"
        elif key == "Icon":
            line = f"Icon={app_name}"
        entry.append(line)

    present = {line.split("=", 1)[0] for line in entry}
    required = (("Type", "Application"), ("Name", display_name),
                ("Exec", app_name), ("Icon", app_name),
                ("Terminal", "true" if terminal else "false"),
                ("Categories", "Utility;"))
    missing = [f"{key}={value}" for key, value in required if key not in present]

    lines[start + 1:end] = missing + entry
    return "\n".join(lines) + "\n"


def render_exec(project: Project, py_version: str) -> str:
    python = f'"$HERE/usr/bin/python{py_version}"'
    entry = project.entry
    if entry.kind == "module":
        return f'exec {python} -m {shlex.quote(entry.target)} "$@"\n'
    if entry.kind == "script":
        return f'exec {python} "$HERE/usr/app/"{shlex.quote(entry.target)} "$@"\n'
    module, _, attr = entry.target.partition(":")
    code = ("import functools,importlib,sys;"
            f"sys.argv[0]={json.dumps(project.app_name)};"
            f"sys.exit(functools.reduce(getattr,{json.dumps(attr)}.split('.'),"
            f"importlib.import_module({json.dumps(module)}))())")
    return f'exec {python} -c {shlex.quote(code)} "$@"\n'


def render_apprun(project: Project, py_version: str, app_type: str) -> str:
    python_path = '"$HERE/usr/app"'
    if project.has_src_dir:
        python_path += ':"$HERE/usr/app/src"'

    script = APPRUN_HEAD.replace("@PYTHONPATH@", python_path)
    if app_type == "cli":
        guard = f"{PROG.upper()}_TERMINAL"
        script += (APPRUN_TERMINAL.replace("@GUARD@", guard)
                   .replace("@PROG@", PROG))
    return script + render_exec(project, py_version)


def make_world_readable(root: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                continue
            mode = info.st_mode | 0o444
            if stat.S_ISDIR(info.st_mode) or info.st_mode & 0o111:
                mode |= 0o111
            os.chmod(path, stat.S_IMODE(mode))
    os.chmod(root, 0o755)


def human_size(size: float) -> str:
    for unit in ("B", "K", "M", "G"):
        if size < 1024 or unit == "G":
            return f"{size:.0f}{unit}"
        size /= 1024
    return f"{size:.0f}G"


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


def _terminate(signum, frame) -> None:
    raise SystemExit(128 + signum)


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    signal.signal(signal.SIGTERM, _terminate)

    try:
        if not argv:
            print(render_help())
            return 0

        config = parse_args(argv)
        log.quiet = config.quiet
        run(config)
    except UsageError as exc:
        print(f"{PROG}: {exc}\nTry '{PROG} --help' for more information.",
              file=sys.stderr)
        return 2
    except Error as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    except OSError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
