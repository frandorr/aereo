"""Generic download module for AEREO extraction pipelines.

Provides Hamilton nodes for downloading and extracting asset archives.
Registered under the ``aereo.download`` entry-point group.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aereo.asset_downloader import (
    download_assets_safely,
    extract_asset_safely,
)
from aereo.interfaces import Extractor

supported_collections: tuple[str, ...] = ("*",)


def local_dir(task: Any) -> Path:
    """Derive a local download directory from the task URI.

    Args:
        task: ExtractionTask (or any object with a ``uri`` attribute).

    Returns:
        A ``pathlib.Path`` pointing to the download directory, created if
        it does not exist.
    """
    uri = getattr(task, "uri", "")
    if uri and not uri.startswith(("s3://", "gs://", "az://", "http://", "https://")):
        path = Path(uri) / "downloads"
    else:
        path = Path("/tmp/aereo-downloads")
    path.mkdir(parents=True, exist_ok=True)
    return path


def download_assets(
    task: Any,
    local_dir: Path,
    max_workers: int | None = None,
    store_options: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Download all assets referenced by *task* to *local_dir*.

    Uses :func:`aereo.asset_downloader.download_assets_safely` for
    concurrent, file-locked downloads.

    Args:
        task: ExtractionTask containing ``assets`` (GeoDataFrame with
            ``id`` and ``href`` columns) and ``profile``.
        local_dir: Directory where assets are written.
        max_workers: Maximum concurrent download threads. ``None`` lets
            :class:`~concurrent.futures.ThreadPoolExecutor` choose.
        store_options: Optional dict forwarded to the obstore store
            constructor (e.g. S3 credentials).

    Returns:
        Mapping of asset ``id`` to the local ``Path`` where it was saved.
    """
    assets = getattr(task, "assets", None)
    if assets is None or len(assets) == 0:
        return {}

    downloader = Extractor.resolve_downloader(task)

    hrefs: list[str] = []
    local_paths: list[Path] = []
    id_to_path: dict[str, Path] = {}

    for _, row in assets.iterrows():
        asset_id = row["id"]
        href = row["href"]
        local_path = local_dir / f"{asset_id}_{Path(href).name}"
        hrefs.append(href)
        local_paths.append(local_path)
        id_to_path[asset_id] = local_path

    download_assets_safely(
        hrefs=hrefs,
        local_paths=local_paths,
        downloader=downloader,
        store_options=store_options or {},
        max_workers=max_workers,
    )

    return id_to_path


def extracted_assets(
    download_assets: dict[str, Path],
    extract_archives: bool = True,
) -> dict[str, Path]:
    """Extract zip archives produced by the download stage.

    Args:
        download_assets: Mapping of asset id to local file path.
        extract_archives: When ``True`` (default), ``.zip`` files are
            extracted to a sibling directory and the directory path is
            returned instead of the archive path.

    Returns:
        Mapping of asset id to file or directory path. Non-zip files are
        forwarded unchanged.
    """
    if not extract_archives:
        return download_assets

    result: dict[str, Path] = {}
    for asset_id, path in download_assets.items():
        if path.suffix.lower() == ".zip":
            extract_dir = path.with_suffix("")
            extract_asset_safely(path, extract_dir=extract_dir)
            result[asset_id] = extract_dir
        else:
            result[asset_id] = path
    return result
