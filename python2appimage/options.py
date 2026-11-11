"""Command-line option table, help/version text and the argparse parser."""
from __future__ import annotations

import argparse
import dataclasses
import re
import textwrap
from typing import List, Optional, Tuple

from .constants import (APP_TYPES, AUTHOR, DEFAULT_PYTHON_VERSION, DEFAULT_TYPE,
                        HELP_WIDTH, PROG, REPO_URL, VERSION)
from .errors import UsageError


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
