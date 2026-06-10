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
from urllib.parse import urlparse

from aereo.asset_downloader._obstore_utils import (
    _resolve_store,
    _stream_obstore_to_disk,
)

DownloaderCallable = Callable[[str, Path], None]


def _download_with_earthaccess(url: str, local_path: Path) -> None:
    """Download *url* to *local_path* using an authenticated earthaccess session.

    This helper is used as a fallback when S3 direct access fails for NASA
    Earthdata assets.  It calls ``earthaccess.login()`` (which reads from
    ``~/.netrc`` when no explicit credentials are given) and then streams
    the file through an authenticated ``requests`` session.

    Args:
        url: HTTPS URL of the Earthdata granule to download.
        local_path: Destination file path on the local filesystem.

    Raises:
        ImportError: If ``earthaccess`` is not installed.
        RuntimeError: If the download fails (non-2xx status).
    """
    import earthaccess  # type: ignore[import-untyped]

    earthaccess.login(persist=True)
    session = earthaccess.get_requests_https_session()
    response = session.get(url, stream=True)
    response.raise_for_status()
    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


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
    fallback_href: str | None = None,
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
        fallback_href: Optional fallback URL to try if the primary *href*
            fails (e.g. an HTTPS URL when cross-region S3 direct access
            is unavailable).
    """
    local_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = local_path.with_suffix(".lock")

    with filelock.FileLock(str(lock_path), timeout=600):
        if not local_path.exists():
            if downloader is not None:
                downloader(href, local_path)
            else:
                try:
                    store, path = _resolve_store(href, store_options)
                    _stream_obstore_to_disk(store, path, local_path)
                except Exception:
                    if fallback_href:
                        # For NASA Earthdata HTTPS fallbacks (when primary
                        # was S3), use earthaccess which handles auth via
                        # ~/.netrc.  This avoids cross-region S3 failures.
                        if (
                            fallback_href.startswith("https://")
                            and href.startswith("s3://")
                            and "nasa.gov" in urlparse(fallback_href).netloc
                        ):
                            _download_with_earthaccess(fallback_href, local_path)
                        else:
                            store, path = _resolve_store(fallback_href, store_options)
                            _stream_obstore_to_disk(store, path, local_path)
                    else:
                        raise


def download_assets_safely(
    hrefs: list[str],
    local_paths: list[Path],
    downloader: DownloaderCallable | None = None,
    store_options: dict[str, Any] | None = None,
    fallback_hrefs: list[str | None] | None = None,
    max_workers: int | None = None,
) -> None:
    """Download multiple assets concurrently using a thread pool.

    Args:
        hrefs: List of URLs or local paths to the assets.
        local_paths: List of destination paths for the downloaded files.
        downloader: Optional callable that handles the download itself.
        store_options: Optional dict forwarded to the obstore store constructor
            for every asset.  See :func:`download_asset_safely` for details.
        fallback_hrefs: Optional list of fallback URLs, one per asset.
            See :func:`download_asset_safely` for details.
        max_workers: Maximum number of worker threads. If ``None``, the
            default is ``min(32, os.cpu_count() + 4)`` as defined by
            :class:`concurrent.futures.ThreadPoolExecutor`.

    Raises:
        ValueError: If *hrefs* and *local_paths* have different lengths.
    """
    if len(hrefs) != len(local_paths):
        raise ValueError("hrefs and local_paths must have the same length")
    if fallback_hrefs is not None and len(fallback_hrefs) != len(hrefs):
        raise ValueError("fallback_hrefs and hrefs must have the same length")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                download_asset_safely,
                href=href,
                local_path=local_path,
                downloader=downloader,
                store_options=store_options,
                fallback_href=fallback_hrefs[i] if fallback_hrefs else None,
            )
            for i, (href, local_path) in enumerate(zip(hrefs, local_paths, strict=True))
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


def cleanup_task_assets(local_paths: list[str], task: Any) -> None:
    """Remove downloaded assets, respecting chunked-task context.

    Args:
        local_paths: List of local file paths to clean up.
        task: The extraction task (used to read ``chunk_id`` / ``total_chunks``
            from ``task_context``).
    """
    for local_path in local_paths:
        cleanup_asset_safely(
            local_path=Path(local_path),
            chunk_id=task.task_context.get("chunk_id"),
            total_chunks=task.task_context.get("total_chunks", 1),
        )


def extract_archives(local_paths: list[str]) -> list[str]:
    """Expand ZIP archives (e.g. Sentinel-3 ``.SEN3`` products) and return ready paths.

    Uses :func:`extract_asset_safely` so that concurrent workers never
    partially overwrite the same extraction directory.

    Non-ZIP paths are returned unchanged.

    Args:
        local_paths: List of local file paths (may include ``.zip`` files).

    Returns:
        List of scene-ready file paths with archives expanded.
    """
    scene_paths: list[str] = []
    for p in local_paths:
        path = Path(p)
        if path.suffix == ".zip":
            extract_dir = path.parent / path.stem
            extract_asset_safely(path, extract_dir)
            scene_paths.append(str(extract_dir))
        else:
            scene_paths.append(str(p))
    return scene_paths


def download_task_assets(
    task: Any,
    *,
    downloader: Any | None = None,
    download_workers: int | None = None,
) -> list[str]:
    """Download every file referenced in *task* and return local paths.

    When a custom *downloader* is configured, HTTPS URLs are preferred over S3
    so that the downloader receives a scheme it can handle.

    Args:
        task: The extraction task containing asset references.
        downloader: Optional custom downloader callable.
        download_workers: Max threads for concurrent asset downloads.

    Returns:
        List of local filesystem paths to the downloaded assets.
    """
    hrefs: list[str] = []
    local_paths: list[Path] = []
    fallback_hrefs: list[str | None] = []
    for _, row in task.assets.iterrows():
        href = str(row["href"])
        https_url = row.get("https_url")
        if downloader is not None and https_url:
            href = str(https_url)
        hrefs.append(href)
        fallback_hrefs.append(str(https_url) if https_url else None)
        local_path = Path(task.uri).absolute() / Path(href).name
        local_paths.append(local_path)

    download_assets_safely(
        hrefs=hrefs,
        local_paths=local_paths,
        downloader=downloader,
        fallback_hrefs=fallback_hrefs,
        max_workers=download_workers,
    )

    return [str(lp) for lp in local_paths]
