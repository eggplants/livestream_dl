""".. include:: ../README.md"""

from __future__ import annotations

import importlib.metadata

from .download_live import LiveStreamDownloader

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"


__all__ = (
    "LiveStreamDownloader",
    "__version__",
)
