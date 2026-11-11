"""python2appimage: build an AppImage from a Python project."""
import sys

if sys.version_info < (3, 8):
    sys.exit("python2appimage: Python 3.8 or newer is required")

from .constants import VERSION as __version__  # noqa: E402

__all__ = ["__version__"]
