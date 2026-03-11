"""Smart download orchestrator.

Auto-selects the best available download backend:
- **aria2** if ``aria2c`` is found on ``$PATH`` (fast, multi-connection).
- **raw**   pure-Python fallback using ``urllib`` + ``ThreadPoolExecutor``.

This base imports from both ``downloader_aria2`` and ``downloader_raw``
components without creating circular dependencies, since neither backend
depends on this base.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

from aer.downloader import DownloadedResultSchema
from aer.downloader_aria2 import download_aria2
from aer.downloader_raw import download_raw
from aer.search import SearchResultSchema

logger = get_logger()


def download(
    gdf: GeoDataFrame["SearchResultSchema"],
    dest_dir: Path | str,
    *,
    max_concurrent: int = 5,
    timeout: int = 600,
    verbose: bool = False,
    headers: dict[str, str] | None = None,
    options: dict[str, Any] | None = None,
    extra_args: list[str] | None = None,
    **kwargs: Any,
) -> GeoDataFrame["DownloadedResultSchema"]:
    """Download files using the best available backend.

    If ``aria2c`` is on ``$PATH`` the aria2 backend is used for maximum
    throughput.  Otherwise, the pure-Python raw backend is selected and a
    warning is emitted.

    Args:
        gdf: DataFrame of search results to download.
        dest_dir: Local directory where files should be saved.
        max_concurrent: Max number of parallel downloads (default 5).
        timeout: Overall timeout in seconds (default 600).
        verbose: If ``True``, logs progress.
        headers: Optional mapping of extra HTTP headers
            (e.g. ``Authorization: Bearer …``).
        options: Backend-specific options (forwarded to aria2 only).
        extra_args: Additional CLI flags (forwarded to aria2 only).
        **kwargs: Reserved for forward compatibility.

    Returns:
        A new GeoDataFrame conforming to
        :class:`~aer.downloader.DownloadedResultSchema`.
    """
    if shutil.which("aria2c"):
        return download_aria2(
            gdf,
            dest_dir,
            max_concurrent=max_concurrent,
            timeout=timeout,
            verbose=verbose,
            headers=headers,
            options=options,
            extra_args=extra_args,
            **kwargs,
        )

    logger.warning(
        "aria2c_not_found",
        message="aria2c is not on PATH — falling back to the raw Python backend.",
    )
    return download_raw(
        gdf,
        dest_dir,
        max_concurrent=max_concurrent,
        timeout=timeout,
        verbose=verbose,
        headers=headers,
        options=options,
        extra_args=extra_args,
        **kwargs,
    )
