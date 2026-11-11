"""Tiny stderr logger shared by all modules."""
from __future__ import annotations

import sys

from .constants import PROG


class Logger:

    def __init__(self) -> None:
        self.quiet = False

    def info(self, message: str) -> None:
        if not self.quiet:
            print(f"{PROG}: {message}", file=sys.stderr)

    def warn(self, message: str) -> None:
        print(f"{PROG}: warning: {message}", file=sys.stderr)


log = Logger()
