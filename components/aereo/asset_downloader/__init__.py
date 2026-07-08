"""Safe asset downloading and cleanup routines.

This module provides file-lock-protected helpers for downloading,
extracting, and cleaning up assets in multi-process environments.
"""

from __future__ import annotations

from aereo.asset_downloader.core import (
    DownloaderCallable,
    cleanup_asset_safely,
    cleanup_task_assets,
    download_asset_safely,
    download_assets_safely,
    download_task_assets,
    extract_archives,
    extract_asset_safely,
)

__all__ = [
    "DownloaderCallable",
    "cleanup_asset_safely",
    "cleanup_task_assets",
    "download_asset_safely",
    "download_assets_safely",
    "download_task_assets",
    "extract_archives",
    "extract_asset_safely",
]
