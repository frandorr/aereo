"""Built-in downloader plugin for the AEREO pipeline.

Provides a default downloader that materialises remote assets to local storage
and updates ``assets["href"]`` so downstream readers read from disk.
"""

from __future__ import annotations

import attrs
from pydantic import ConfigDict, validate_call

from aereo.asset_downloader import DownloaderCallable, download_task_assets
from aereo.interfaces import ExtractionTask


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def download_assets(
    task: ExtractionTask,
    downloader: DownloaderCallable | None = None,
    download_workers: int | None = None,
) -> ExtractionTask:
    """Download every asset in *task* and update ``assets["href"]`` to local paths.

    Args:
        task: The extraction task containing assets to download.
        downloader: Optional custom downloader callable. If omitted, a default
            obstore-based downloader is used (with Earthdata fallback logic when
            ``s3_credentials_url`` is present).
        download_workers: Max threads for concurrent asset downloads.

    Returns:
        A new ``ExtractionTask`` with ``assets["href"]`` replaced by the
        downloaded local paths. The input task is unchanged.

    Note:
        This downloader updates ``assets["href"]``. Readers that reconstruct
        source URIs from STAC items (e.g. ``read_odc_stac``) are not supported
        unless the caller also patches ``task.assets["stac_item"]``.
    """
    local_paths = download_task_assets(
        task,
        downloader=downloader,
        download_workers=download_workers,
    )

    updated_assets = task.assets.copy()
    updated_assets["href"] = local_paths

    return attrs.evolve(task, assets=updated_assets)
