"""Core implementation of safe, lock-protected asset downloading and extraction routines.

Provides concurrent download and extract utilities designed for multi-process environments.
"""

import filelock
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from aereo.asset_downloader._obstore_utils import (
    _resolve_store,
    _stream_obstore_to_disk,
)

DownloaderCallable = Callable[[str, Path], None]


def _safe_unlink(path: Path) -> None:
    """Remove a file, ignoring errors if it does not exist or is inaccessible."""
    try:
        path.unlink()
    except OSError:
        pass


def download_asset_safely(
    href: str,
    local_path: Path,
    downloader: DownloaderCallable | None = None,
    store_options: dict[str, Any] | None = None,
) -> None:
    """Download asset with a filelock to avoid corruption in multi-processing.

    Args:
        href: URL or local path to the asset. Supported schemes:
            ``s3://``, ``gs://``, ``az://``, ``http(s)://``, ``file://``,
            or a bare local filesystem path.
        local_path: Destination path for the downloaded file.
        downloader: Optional callable that handles the download itself.
            If provided, it is called unconditionally inside the file lock
            and all built-in logic is skipped. This is the escape hatch used
            by plugins such as *aereo-search-earthaccess* that need custom
            authentication or region-fallback logic.
        store_options: Optional dict of keyword arguments forwarded to the
            obstore store constructor.  For ``s3://`` URLs this is passed as
            ``S3Store(bucket, **store_options)``.  Common keys:

            - ``skip_signature=False`` — disable anonymous access.
            - ``access_key_id`` / ``secret_access_key`` / ``token`` —
              explicit AWS credentials.
            - ``credential_provider`` — a callable that returns credentials
              (enables automatic refresh).
    """
    local_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = local_path.with_suffix(".lock")

    with filelock.FileLock(str(lock_path), timeout=600):
        if not local_path.exists():
            if downloader is not None:
                downloader(href, local_path)
            else:
                store, path = _resolve_store(href, store_options)
                _stream_obstore_to_disk(store, path, local_path)


def download_assets_safely(
    hrefs: list[str],
    local_paths: list[Path],
    downloader: DownloaderCallable | None = None,
    store_options: dict[str, Any] | None = None,
    max_workers: int | None = None,
) -> None:
    """Download multiple assets concurrently using a thread pool.

    Args:
        hrefs: List of URLs or local paths to the assets.
        local_paths: List of destination paths for the downloaded files.
        downloader: Optional callable that handles the download itself.
        store_options: Optional dict forwarded to the obstore store constructor
            for every asset.  See :func:`download_asset_safely` for details.
        max_workers: Maximum number of worker threads. If ``None``, the
            default is ``min(32, os.cpu_count() + 4)`` as defined by
            :class:`concurrent.futures.ThreadPoolExecutor`.

    Raises:
        ValueError: If *hrefs* and *local_paths* have different lengths.
    """
    if len(hrefs) != len(local_paths):
        raise ValueError("hrefs and local_paths must have the same length")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                download_asset_safely,
                href=href,
                local_path=local_path,
                downloader=downloader,
                store_options=store_options,
            )
            for href, local_path in zip(hrefs, local_paths, strict=True)
        ]
        for future in futures:
            future.result()


def extract_asset_safely(
    archive_path: Path,
    extract_dir: Path | None = None,
    lock_path: Path | None = None,
) -> None:
    """Extract a zip archive safely with file locking.

    Uses atomic extraction (temp directory + rename) so that other
    processes never see a partially extracted directory.  An
    ``.extracted`` marker file is written on success; if the marker
    exists the function returns immediately.

    Args:
        archive_path: Path to the zip archive.
        extract_dir: Destination directory.  Defaults to
            ``archive_path.with_suffix("")``.
        lock_path: Path to the lock file.  Defaults to
            ``extract_dir.with_suffix(".lock")``.
    """
    archive_path = Path(archive_path)
    if extract_dir is None:
        extract_dir = archive_path.with_suffix("")
    extract_dir = Path(extract_dir)

    if lock_path is None:
        lock_path = extract_dir.with_suffix(".lock")
    lock_path = Path(lock_path)

    marker_path = extract_dir.with_suffix(".extracted")

    with filelock.FileLock(str(lock_path)):
        # Already extracted and marked complete
        if marker_path.exists() and extract_dir.exists():
            return

        # Remove any stale partial extraction
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)

        extract_dir.parent.mkdir(parents=True, exist_ok=True)

        # Extract to a temporary directory so other processes never
        # see an incomplete destination.
        temp_dir = tempfile.mkdtemp(
            prefix=extract_dir.name + "_tmp_",
            dir=extract_dir.parent,
        )
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(temp_dir)

            Path(temp_dir).rename(extract_dir)
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        marker_path.touch()


def cleanup_asset_safely(
    local_path: Path, chunk_id: int | None = None, total_chunks: int = 1
) -> None:
    """Safely clean up a downloaded asset.

    When *total_chunks* is greater than 1 and *chunk_id* is provided,
    the function tracks completion via per-chunk marker files and only
    removes the asset once every chunk has signaled completion.  File
    locking is used to avoid race conditions in multi-processing.

    Args:
        local_path: Path to the downloaded file to remove.
        chunk_id: Identifier of the current chunk (0-based). Used only
            when *total_chunks* is greater than 1.
        total_chunks: Total number of chunks that must complete before
            the asset is removed. Defaults to 1.
    """
    lock_path = local_path.with_suffix(".lock")
    if total_chunks > 1 and chunk_id is not None:
        done_file = local_path.with_suffix(f".chunk_{chunk_id}.done")
        done_file.touch()
        with filelock.FileLock(str(lock_path)):
            done_files = list(local_path.parent.glob(f"{local_path.stem}.chunk_*.done"))
            if len(done_files) >= total_chunks:
                _safe_unlink(local_path)
                for df in done_files:
                    _safe_unlink(df)
                _safe_unlink(lock_path)
    else:
        _safe_unlink(local_path)
