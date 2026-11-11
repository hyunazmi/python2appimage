"""Constants, regular expressions and shell templates."""
from __future__ import annotations

import re

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
