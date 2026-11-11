"""Generation of the .desktop entry and the AppRun launcher script."""
from __future__ import annotations

import json
import shlex
from typing import List

from .constants import APPRUN_HEAD, APPRUN_TERMINAL, PROG
from .project import Project


def rewrite_desktop_entry(text: str, app_name: str, display_name: str,
                          terminal: bool) -> str:
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == "[Desktop Entry]"), None
    )
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
