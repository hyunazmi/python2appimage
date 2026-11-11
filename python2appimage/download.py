"""Network access and cached tools (Python runtime, appimagetool)."""
from __future__ import annotations

import http.client
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .constants import (APPIMAGETOOL_URL, MAX_PAGE_BYTES, PROG,
                        PYTHON_RELEASES_URL, VERSION)
from .errors import Error
from .logger import log


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
