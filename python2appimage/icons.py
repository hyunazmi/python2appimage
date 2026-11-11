"""Icon detection and placeholder generation."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .constants import ICON_DIR_NAMES, ICON_EXTENSIONS
from .fsutils import is_inside, iter_files
from .project import Project


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
