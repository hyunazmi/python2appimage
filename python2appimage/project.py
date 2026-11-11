"""Project detection: name, version, entry point, desktop file, requirements."""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Dict, List, Optional

from .constants import (DIR_VERSION, DOTTED_NAME, IGNORED_SCRIPTS, NON_APP_DIRS,
                        TOML_SECTION, TOML_STRING_PAIR)
from .errors import Error
from .fsutils import is_inside, iter_files


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
