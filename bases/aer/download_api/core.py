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

import pandas as pd
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

from aer.downloader import DownloadedResultSchema, DownloadStatus
from aer.downloader_aria2 import download_aria2
from aer.downloader_raw import download_raw
from aer.search import SearchResultSchema

logger = get_logger()


def _resolve_filename(uri: str) -> str:
    """Derive a filename from the URI's last path segment."""
    return uri.rsplit("/", 1)[-1].split("?")[0] or "download"


def _mark_cached(
    gdf: GeoDataFrame["SearchResultSchema"],
    dest_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split gdf into cached (already downloaded) and needs-download subsets.

    Returns:
        (cached_df, to_download_df) — cached_df has local_path and
        download_status="complete" already set; to_download_df needs the
        backend. Neither is schema-validated; that happens at the final return.
    """
    res = gdf.copy()
    res["local_path"] = pd.Series([None] * len(res), dtype="string", index=res.index)
    res["download_status"] = pd.Series(
        ["skipped"] * len(res), dtype="string", index=res.index
    )

    valid_mask = res["https_url"].notna()
    if not valid_mask.any():
        return res.iloc[:0], res

    uris = res.loc[valid_mask, "https_url"]
    filenames = uris.map(_resolve_filename)
    dest_files = dest_dir / filenames

    exists_mask = pd.Series(
        [f.exists() and f.stat().st_size > 0 for f in dest_files],
        index=uris.index,
    )

    cached_idx = valid_mask & exists_mask
    to_download_idx = valid_mask & ~exists_mask

    if cached_idx.any():
        res.loc[cached_idx, "local_path"] = (
            (dest_dir / filenames[cached_idx]).astype(str).values
        )
        res.loc[cached_idx, "download_status"] = DownloadStatus.COMPLETE.value
        logger.info(
            "download_cache_hit",
            count=int(cached_idx.sum()),
        )

    return res[cached_idx], res[to_download_idx]


def _call_backend(
    backend: str,
    gdf: GeoDataFrame,
    dest_dir: Path | str,
    *,
    max_concurrent: int,
    timeout: int,
    verbose: bool,
    headers: dict[str, str] | None,
    options: dict[str, Any] | None,
    extra_args: list[str] | None,
    **kwargs: Any,
) -> GeoDataFrame:
    """Dispatch to the appropriate download backend."""
    if backend == "aria2":
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

    Files that already exist locally (non-empty) are skipped and returned
    with ``download_status="complete"`` without contacting the backend.

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
    dest_path = Path(dest_dir)

    if len(gdf) == 0:
        res_gdf = gdf.copy()
        res_gdf["local_path"] = pd.Series([], dtype="string")
        res_gdf["download_status"] = pd.Series([], dtype="string")
        return DownloadedResultSchema.validate(res_gdf)

    # Pre-check: skip files that already exist locally
    cached_gdf, to_download_gdf = _mark_cached(gdf, dest_path)

    if len(to_download_gdf) == 0:
        return DownloadedResultSchema.validate(cached_gdf)

    # Select backend
    if shutil.which("aria2c"):
        backend = "aria2"
    else:
        logger.warning(
            "aria2c_not_found",
            message="aria2c is not on PATH — falling back to the raw Python backend.",
        )
        backend = "raw"

    downloaded_gdf = _call_backend(
        backend,
        to_download_gdf,
        dest_dir,
        max_concurrent=max_concurrent,
        timeout=timeout,
        verbose=verbose,
        headers=headers,
        options=options,
        extra_args=extra_args,
        **kwargs,
    )

    if len(cached_gdf) == 0:
        return downloaded_gdf

    combined = pd.concat([cached_gdf, downloaded_gdf], ignore_index=False)
    combined = combined.sort_index()
    return DownloadedResultSchema.validate(combined)
