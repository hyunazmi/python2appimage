"""Command-line entry point."""
from __future__ import annotations

import os
import signal
import sys
from typing import Optional, Sequence

from .builder import run
from .config import parse_args
from .constants import PROG
from .errors import Error, UsageError
from .logger import log
from .options import render_help


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
