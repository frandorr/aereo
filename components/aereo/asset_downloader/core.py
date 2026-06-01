import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from aereo.asset_downloader._obstore_utils import (
    _resolve_store,
    _stream_obstore_to_disk,
)

if TYPE_CHECKING:
    from aereo.interfaces import DownloaderCallable


def download_asset_safely(
    href: str,
    local_path: Path,
    downloader: Optional["DownloaderCallable"] = None,
    store_options: Optional[dict[str, Any]] = None,
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
    import filelock

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
    downloader: Optional["DownloaderCallable"] = None,
    store_options: Optional[dict[str, Any]] = None,
    max_workers: Optional[int] = None,
) -> None:
    """Download multiple assets concurrently using a thread pool.

    Args:
        hrefs: List of URLs or local paths to the assets.
        local_paths: List of destination paths for the downloaded files.
        downloader: Optional callable that handles the download itself.
        store_options: Optional dict forwarded to the obstore store constructor
            for every asset.  See :func:`download_asset_safely` for details.
        max_workers: The maximum number of threads to use. Defaults to None.
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
    extract_dir: Optional[Path] = None,
    lock_path: Optional[Path] = None,
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
    import filelock
    import tempfile
    import zipfile

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
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        marker_path.touch()


def cleanup_asset_safely(
    local_path: Path, chunk_id: Optional[int] = None, total_chunks: int = 1
) -> None:
    """Safely clean up the downloaded asset after all chunks are processed."""
    import filelock

    lock_path = local_path.with_suffix(".lock")
    if total_chunks > 1 and chunk_id is not None:
        done_file = local_path.with_suffix(f".chunk_{chunk_id}.done")
        done_file.touch()
        with filelock.FileLock(str(lock_path)):
            done_files = list(local_path.parent.glob(f"{local_path.stem}.chunk_*.done"))
            if len(done_files) >= total_chunks:
                if local_path.exists():
                    try:
                        local_path.unlink()
                    except Exception:
                        pass
                for df in done_files:
                    try:
                        df.unlink()
                    except Exception:
                        pass
                try:
                    lock_path.unlink()
                except Exception:
                    pass
    else:
        if local_path.exists():
            try:
                local_path.unlink()
            except Exception:
                pass
