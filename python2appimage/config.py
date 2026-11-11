"""Validated runtime configuration built from command-line arguments."""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Optional, Sequence

from .constants import APP_TYPES, ICON_EXTENSIONS
from .errors import Error, UsageError
from .options import build_parser


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
