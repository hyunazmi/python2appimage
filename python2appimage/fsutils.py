"""Filesystem helpers."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Iterator, Optional

from .constants import PRUNE_DIRS


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
