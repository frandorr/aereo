"""Aria2-based download backend using the ``aria2c`` CLI directly.

Downloads files via HTTP/HTTPS by invoking ``aria2c`` as a subprocess.
All requests run in parallel via a single ``aria2c -i input_file`` call.

The module is **protocol-agnostic**: it receives HTTPS/HTTP URIs and downloads
them. S3-to-HTTPS conversion is the caller's responsibility (see
``aer.downloader.s3_uri_to_https``).

Usage::

    from aer.downloader import DownloadRequest, DownloadMethod

    reqs = [
        DownloadRequest(
            uri="https://ladsweb.modaps.eosdis.nasa.gov/archive/file.hdf",
            dest_dir="/data/downloads",
            headers={"Authorization": "Bearer <token>"},
        ),
    ]

    dl = DownloadMethod.get("aria2")
    results = dl(reqs, max_concurrent=4)
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from structlog import get_logger

from aer.downloader import (
    DownloadRequest,
    DownloadResult,
    DownloadStatus,
)

logger = get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_filename(req: DownloadRequest) -> str:
    """Derive a filename from the request or the URI's last path segment."""
    if req.filename:
        return str(req.filename)
    return str(req.uri.rsplit("/", 1)[-1].split("?")[0] or "download")


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
    requests: list[DownloadRequest],
    filenames: list[str],
    path: Path,
) -> None:
    """Write an aria2c input file with per-URI options.

    Format (from aria2c docs)::

        URI
          dir=/path/to/dir
          out=filename
          header=Authorization: Bearer xyz

    Entries are separated by blank lines.
    """
    lines: list[str] = []
    for req, filename in zip(requests, filenames):
        lines.append(req.uri)
        lines.append(f"  dir={req.dest_dir}")
        lines.append(f"  out={filename}")
        for key, value in req.headers.items():
            lines.append(f"  header={key}: {value}")
        for opt_key, opt_val in req.options.items():
            lines.append(f"  {opt_key}={opt_val}")
        lines.append("")  # blank line separates entries

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public download function
# ---------------------------------------------------------------------------


def download_aria2(
    requests: list[DownloadRequest],
    *,
    max_concurrent: int = 5,
    timeout: int = 600,
    verbose: bool = False,
    extra_args: list[str] | None = None,
    **kwargs: Any,
) -> list[DownloadResult]:
    """Download files in parallel using a single ``aria2c -i`` call.

    All requests are written to a temporary input file and processed
    by one ``aria2c`` invocation.  Aria2c handles parallelism natively
    via ``--max-concurrent-downloads``.

    URIs must be HTTP/HTTPS.  For S3 URIs, convert them first with
    ``aer.downloader.s3_uri_to_https`` before creating the requests.

    Args:
        requests: Download requests to process.
        max_concurrent: Max number of parallel downloads (default 5).
        timeout: Overall timeout in seconds (default 600).
        verbose: If ``True``, aria2c prints real-time download progress
            (speed, ETA, percentage) directly to the console.
        extra_args: Additional CLI flags forwarded to ``aria2c``.
        **kwargs: Reserved for forward compatibility.

    Returns:
        A list of ``DownloadResult`` in the same order as *requests*.

    Raises:
        FileNotFoundError: If ``aria2c`` is not installed.
    """
    if not requests:
        return []

    aria2c = _ensure_aria2c()

    # Resolve filenames and ensure dest dirs exist
    filenames: list[str] = []
    for req in requests:
        filenames.append(_resolve_filename(req))
        req.dest_dir.mkdir(parents=True, exist_ok=True)

    # Write the input file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="aria2_downloads_",
        delete=False,
    ) as tmp:
        input_file = Path(tmp.name)

    _write_input_file(requests, filenames, input_file)

    logger.info(
        "download_batch_started",
        count=len(requests),
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
        # Console output level: verbose shows real-time progress
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
    except subprocess.TimeoutExpired:
        logger.warning("download_batch_timeout", timeout=timeout)
        # All requests timed out
        return [
            DownloadResult(
                request=req,
                status=DownloadStatus.FAILED,
                error=f"Batch timed out after {timeout}s",
            )
            for req in requests
        ]
    except Exception as exc:
        logger.error("download_batch_error", error=str(exc))
        return [
            DownloadResult(
                request=req,
                status=DownloadStatus.FAILED,
                error=str(exc),
            )
            for req in requests
        ]
    finally:
        # Clean up the input file
        input_file.unlink(missing_ok=True)

    # Build results by checking which files actually landed on disk
    results: list[DownloadResult] = []
    for req, filename in zip(requests, filenames):
        dest_path = req.dest_dir / filename
        if dest_path.exists():
            size = dest_path.stat().st_size
            logger.info(
                "download_complete",
                uri=req.uri,
                path=str(dest_path),
                bytes=size,
            )
            results.append(
                DownloadResult(
                    request=req,
                    status=DownloadStatus.COMPLETE,
                    path=dest_path,
                    bytes_downloaded=size,
                )
            )
        else:
            error_msg = (
                error_output
                if aria2_failed
                else f"File not found after download: {dest_path}"
            )
            logger.warning(
                "download_failed",
                uri=req.uri,
                error=error_msg,
            )
            results.append(
                DownloadResult(
                    request=req,
                    status=DownloadStatus.FAILED,
                    error=error_msg,
                )
            )

    return results


# ---------------------------------------------------------------------------
# End of file
# ---------------------------------------------------------------------------
