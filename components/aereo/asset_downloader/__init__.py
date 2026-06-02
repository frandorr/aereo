"""Safe asset downloading and cleanup routines.

This module provides file-lock-protected helpers for downloading,
extracting, and cleaning up assets in multi-process environments.
"""

from __future__ import annotations

from aereo.asset_downloader.core import (
    cleanup_asset_safely,
    download_asset_safely,
    download_assets_safely,
    extract_asset_safely,
)

__all__ = [
    "cleanup_asset_safely",
    "download_asset_safely",
    "download_assets_safely",
    "extract_asset_safely",
]
