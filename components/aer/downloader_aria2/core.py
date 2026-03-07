"""Aria2-based download backend using the ``aria2c`` CLI directly.

Downloads files via HTTP/HTTPS by invoking ``aria2c`` as a subprocess.
All requests run in parallel via a single ``aria2c -i input_file`` call.

The module is **protocol-agnostic**: it receives HTTPS/HTTP URIs and downloads
them. S3-to-HTTPS conversion is the caller's responsibility (see
``aer.downloader.s3_uri_to_https``).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

from aer.downloader import DownloadedResultSchema, DownloadStatus
from aer.plugin import plugin
from aer.search import SearchResultSchema

logger = get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_filename(uri: str) -> str:
    """Derive a filename from the URI's last path segment."""
    return uri.rsplit("/", 1)[-1].split("?")[0] or "download"


def _ensure_aria2c() -> str:
    """Return the path to ``aria2c`` or raise ``FileNotFoundError``."""
    path = shutil.which("aria2c")
    if path is None:
        raise FileNotFoundError(
            "aria2c is not installed or not on PATH. "
            "Install it with: apt-get install aria2  (Debian/Ubuntu) "
            "or brew install aria2  (macOS)."
        )
    return path


def _write_input_file(
    uris: list[str],
    filenames: list[str],
    dest_dir: Path,
    path: Path,
    headers: dict[str, str] | None = None,
    options: dict[str, Any] | None = None,
) -> None:
    """Write an aria2c input file with per-URI options."""
    headers = headers or {}
    options = options or {}
    lines: list[str] = []

    for uri, filename in zip(uris, filenames):
        lines.append(uri)
        lines.append(f"  dir={dest_dir}")
        lines.append(f"  out={filename}")
        for key, value in headers.items():
            lines.append(f"  header={key}: {value}")
        for opt_key, opt_val in options.items():
            lines.append(f"  {opt_key}={opt_val}")
        lines.append("")  # blank line separates entries

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public download function
# ---------------------------------------------------------------------------


@plugin(name="aria2", category="download")
def download_aria2(
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
    """Download files in parallel using a single ``aria2c -i`` call.

    All requests are written to a temporary input file and processed
    by one ``aria2c`` invocation.  Aria2c handles parallelism natively
    via ``--max-concurrent-downloads``.

    Args:
        gdf: DataFrame of search results to download.
        dest_dir: Local directory where files should be saved.
        max_concurrent: Max number of parallel downloads (default 5).
        timeout: Overall timeout in seconds (default 600).
        verbose: If ``True``, aria2c prints real-time download progress.
        headers: Optional mapping of extra HTTP headers (e.g. ``Authorization: Bearer …``).
        options: Backend-specific options forwarded as-is to aria2.
        extra_args: Additional CLI flags forwarded to ``aria2c``.
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

    aria2c = _ensure_aria2c()

    # Resolve filenames and ensure dest dirs exist
    filenames: list[str] = [_resolve_filename(uri) for uri in uris]
    dest_path.mkdir(parents=True, exist_ok=True)

    # Write the input file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="aria2_downloads_",
        delete=False,
    ) as tmp:
        input_file = Path(tmp.name)

    _write_input_file(uris, filenames, dest_path, input_file, headers, options)

    logger.info(
        "download_batch_started",
        count=len(uris),
        input_file=str(input_file),
        max_concurrent=max_concurrent,
    )

    # Build the aria2c command
    cmd: list[str] = [
        aria2c,
        f"--input-file={input_file}",
        f"--max-concurrent-downloads={max_concurrent}",
        "--max-connection-per-server=4",
        "--split=4",
        "--min-split-size=1M",
        f"--timeout={timeout}",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--max-tries=3",
        "--retry-wait=5",
        f"--console-log-level={'notice' if verbose else 'warn'}",
        f"--summary-interval={'1' if verbose else '0'}",
    ]

    if extra_args:
        cmd.extend(extra_args)

    # Run aria2c
    try:
        proc = subprocess.run(
            cmd,
            capture_output=not verbose,
            text=True,
            timeout=timeout + 30,
        )
        aria2_failed = proc.returncode != 0
        error_output = ""
        if not verbose and aria2_failed:
            error_output = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        batch_timed_out = False
    except subprocess.TimeoutExpired:
        logger.warning("download_batch_timeout", timeout=timeout)
        aria2_failed = True
        error_output = f"Batch timed out after {timeout}s"
        batch_timed_out = True
    except Exception as exc:
        logger.error("download_batch_error", error=str(exc))
        aria2_failed = True
        error_output = str(exc)
        batch_timed_out = True
    finally:
        # Clean up the input file
        input_file.unlink(missing_ok=True)

    # Build results array
    local_paths: list[str | None] = []
    statuses: list[str] = []

    for uri, filename in zip(uris, filenames):
        if batch_timed_out:
            local_paths.append(None)
            statuses.append(DownloadStatus.FAILED.value)
            continue

        dest_file = dest_path / filename
        if dest_file.exists() and dest_file.stat().st_size > 0:
            size_bytes = dest_file.stat().st_size
            logger.info(
                "download_complete",
                uri=uri,
                path=str(dest_file),
                bytes=size_bytes,
            )
            local_paths.append(str(dest_file))
            statuses.append(DownloadStatus.COMPLETE.value)
        else:
            local_paths.append(None)
            statuses.append(DownloadStatus.FAILED.value)
            if not aria2_failed:
                error_msg = f"File not found or empty after download: {dest_file}"
            else:
                error_msg = error_output
            logger.warning(
                "download_failed",
                uri=uri,
                error=error_msg,
            )

    # Re-assign back to res_gdf using the valid index
    res_gdf.loc[valid_mask, "local_path"] = local_paths
    res_gdf.loc[valid_mask, "download_status"] = statuses

    return DownloadedResultSchema.validate(res_gdf)
