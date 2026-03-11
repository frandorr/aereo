"""Raw Python multithreaded download backend using only standard library.

Downloads files via HTTP/HTTPS concurrently using `concurrent.futures.ThreadPoolExecutor`
and `urllib.request`. It acts as a protocol-agnostic alternative to `downloader_aria2`.
"""

from __future__ import annotations

import concurrent.futures
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

from aer.downloader import DownloadedResultSchema, DownloadStatus
from aer.search import SearchResultSchema

logger = get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_filename(uri: str) -> str:
    """Derive a filename from the URI's last path segment."""
    return uri.rsplit("/", 1)[-1].split("?")[0] or "download"


def _download_single_file(
    uri: str,
    dest_file: Path,
    timeout: int,
    headers: dict[str, str] | None = None,
) -> tuple[str, str, str | None]:
    """Download a single file.

    Returns:
        A tuple of (uri, status, error_msg or None).
    """
    req = urllib.request.Request(uri)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    # Use a temporary file to prevent partial downloads
    with tempfile.NamedTemporaryFile(dir=dest_file.parent, delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                shutil.copyfileobj(response, tmp_file)
        except urllib.error.URLError as e:
            tmp_path.unlink(missing_ok=True)
            return (uri, DownloadStatus.FAILED.value, str(e.reason))
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            return (uri, DownloadStatus.FAILED.value, str(e))

    try:
        # Atomic replace after closing the temp file
        tmp_path.replace(dest_file)
        if dest_file.exists() and dest_file.stat().st_size > 0:
            return (uri, DownloadStatus.COMPLETE.value, None)
        else:
            return (
                uri,
                DownloadStatus.FAILED.value,
                "File not found or empty after download",
            )
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        return (uri, DownloadStatus.FAILED.value, str(e))


# ---------------------------------------------------------------------------
# Public download function
# ---------------------------------------------------------------------------


def download_raw(
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
    """Download files in parallel using Python's standard library.

    Args:
        gdf: DataFrame of search results to download.
        dest_dir: Local directory where files should be saved.
        max_concurrent: Max number of parallel downloads (default 5).
        timeout: Overall timeout in seconds per file (default 600).
        verbose: If ``True``, logs progress.
        headers: Optional mapping of extra HTTP headers (e.g. ``Authorization: Bearer …``).
        options: Ignored by raw downloader.
        extra_args: Ignored by raw downloader.
        **kwargs: Reserved for forward compatibility.

    Returns:
        A new GeoDataFrame conforming to DownloadedResultSchema.
    """
    dest_path = Path(dest_dir)
    res_gdf = gdf.copy()

    import pandas as pd

    if len(res_gdf) == 0:
        res_gdf["local_path"] = pd.Series([], dtype="string")
        res_gdf["download_status"] = pd.Series([], dtype="string")
        return DownloadedResultSchema.validate(res_gdf)

    # Initialize new columns
    res_gdf["local_path"] = pd.Series(
        [None] * len(res_gdf), dtype="string", index=res_gdf.index
    )
    res_gdf["download_status"] = pd.Series(
        ["skipped"] * len(res_gdf), dtype="string", index=res_gdf.index
    )

    valid_mask = res_gdf["https_url"].notna()
    if not valid_mask.any():
        return DownloadedResultSchema.validate(res_gdf)

    # Filter valid URLs to download
    to_download = res_gdf[valid_mask]
    uris = to_download["https_url"].tolist()

    filenames = [_resolve_filename(uri) for uri in uris]
    dest_path.mkdir(parents=True, exist_ok=True)

    logger.info(
        "download_batch_started",
        count=len(uris),
        backend="raw",
        max_concurrent=max_concurrent,
    )

    results_map: dict[str, tuple[str, str | None]] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_uri = {
            executor.submit(
                _download_single_file,
                uri,
                dest_path / filename,
                timeout,
                headers,
            ): uri
            for uri, filename in zip(uris, filenames)
        }

        for future in concurrent.futures.as_completed(future_to_uri):
            uri = future_to_uri[future]
            try:
                # The _download_single_file function returns (uri, status, error_msg)
                res_uri, status, error_msg = future.result()
            except Exception as exc:
                status = DownloadStatus.FAILED.value
                error_msg = f"Unexpected error: {exc}"

            results_map[uri] = (status, error_msg)

    # Build results array based on the original uri list to maintain the index
    local_paths: list[str | None] = []
    statuses: list[str] = []

    for uri, filename in zip(uris, filenames):
        status, error_msg = results_map[uri]
        dest_file = dest_path / filename

        if status == DownloadStatus.COMPLETE.value:
            if verbose:
                logger.info(
                    "download_complete",
                    uri=uri,
                    path=str(dest_file),
                )
            local_paths.append(str(dest_file))
            statuses.append(status)
        else:
            local_paths.append(None)
            statuses.append(status)
            logger.warning(
                "download_failed",
                uri=uri,
                error=error_msg,
            )

    # Re-assign back to res_gdf using the valid index
    res_gdf.loc[valid_mask, "local_path"] = local_paths
    res_gdf.loc[valid_mask, "download_status"] = statuses

    return DownloadedResultSchema.validate(res_gdf)
