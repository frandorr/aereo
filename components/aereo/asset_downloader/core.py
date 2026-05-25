import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from aereo.interfaces import Downloader


def download_asset_safely(
    href: str,
    local_path: Path,
    s3_client: Optional[Any] = None,
    http_session: Optional[Any] = None,
    downloader: Optional["Downloader"] = None,
) -> None:
    """Download asset with a filelock to avoid corruption in multi-processing.

    Args:
        href: URL or local path to the asset.
        local_path: Destination path for the downloaded file.
        s3_client: Optional authenticated S3FileSystem for S3 access.
            Note: Only works when running in AWS us-west-2 region.
        http_session: Optional authenticated requests.Session for HTTPS downloads.
            Use earthaccess.get_requests_https_session() to create.
            Works from anywhere (no AWS region requirement).
        downloader: Optional callable that handles the download itself.
            If provided, it is called unconditionally inside the file lock
            and all built-in logic is skipped.
    """
    import filelock
    import s3fs
    import requests

    local_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = local_path.with_suffix(".lock")

    with filelock.FileLock(str(lock_path)):
        if not local_path.exists():
            if downloader is not None:
                downloader(href, local_path)
            elif href.startswith("s3://"):
                fs = (
                    s3_client if s3_client is not None else s3fs.S3FileSystem(anon=True)
                )
                fs.get(href.replace("s3://", ""), str(local_path))
            elif href.startswith("http://") or href.startswith("https://"):
                http = http_session if http_session is not None else requests
                response = http.get(href, stream=True)
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            elif Path(href).exists():
                if Path(href).absolute() != local_path.absolute():
                    shutil.copy(href, local_path)
            else:
                raise FileNotFoundError(f"Source file not found at {href}")


def download_assets_safely(
    hrefs: list[str],
    local_paths: list[Path],
    s3_client: Optional[Any] = None,
    http_session: Optional[Any] = None,
    downloader: Optional["Downloader"] = None,
    max_workers: Optional[int] = None,
) -> None:
    """Download multiple assets concurrently using a thread pool.

    Args:
        hrefs: List of URLs or local paths to the assets.
        local_paths: List of destination paths for the downloaded files.
        s3_client: Optional authenticated S3FileSystem for S3 access.
        http_session: Optional authenticated requests.Session for HTTPS downloads.
        downloader: Optional callable that handles the download itself.
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
                s3_client=s3_client,
                http_session=http_session,
                downloader=downloader,
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
    import shutil
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
