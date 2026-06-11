"""BatchWriter example: VIIRS I04 extraction with memory-controlled writes.

This script demonstrates the difference between the per-patch ``Writer`` and
the new ``BatchWriter`` using ``BatchWriteGeoTIFF``.

Key points:
- ``Writer`` (e.g. ``WriteGeoTIFF``) receives one patch at a time.
- ``BatchWriter`` (e.g. ``BatchWriteGeoTIFF``) receives the entire
  ``{patch_id: xr.Dataset}`` map, so it can control iteration order,
  batch compute with Dask, and explicitly release memory after each write.
"""

from __future__ import annotations

import pandas as pd
from shapely.geometry import Polygon

from aereo.backends import LocalProcessBackend, TaskRunner
from aereo.builtins import (
    BatchWriteGeoTIFF,
    SearchEarthaccess,
    WriteGeoTIFF,
)
from aereo.client import AereoClient
from aereo.interfaces import ExtractConfig, GridConfig, PatchConfig
from aereo.task_builder import prepare_for_extraction


# ---------------------------------------------------------------------------
# AOIs and temporal window
# ---------------------------------------------------------------------------

POLYGON = Polygon(
    [
        (-69.03309679385858, -38.36049911182725),
        (-68.4091649211404, -38.36049911182725),
        (-68.4091649211404, -38.757366643812944),
        (-69.03309679385858, -38.757366643812944),
        (-69.03309679385858, -38.36049911182725),
    ]
)

START = pd.to_datetime("2024-01-01T00:00:00Z")
END = pd.to_datetime("2024-01-02T00:00:00Z")

# ---------------------------------------------------------------------------
# Grid / patch configuration
# ---------------------------------------------------------------------------

GRID_CONFIG = GridConfig(target_grid_dist=50_000)
PATCH_CONFIG = PatchConfig(resolution=375, margin=10.0)

# ---------------------------------------------------------------------------
# 1. Search for VIIRS assets
# ---------------------------------------------------------------------------

search = SearchEarthaccess(
    collections={"VJ202IMG": ["I04"], "VJ203IMG": []},
    intersects=POLYGON,
    start_datetime=START,
    end_datetime=END,
)
assets = search()
print(f"Found {len(assets)} assets")

# ---------------------------------------------------------------------------
# 2a. Extract with per-patch Writer (classic approach)
# ---------------------------------------------------------------------------


def extract_with_writer():
    """Classic approach: WriteGeoTIFF receives one patch at a time."""
    from aereo.read_satpy import ReadSatpy
    from aereo.reproject_satpy import ReprojectSatpy

    reader = ReadSatpy(wishlist=["I04"], reader="viirs_l1b")
    reprojector = ReprojectSatpy()
    writer = WriteGeoTIFF()

    extract_config = ExtractConfig(
        read=reader,
        reproject=reprojector,
        write=writer,
    )

    tasks = prepare_for_extraction(
        search_results=assets,
        grid_config=GRID_CONFIG,
        patch_config=PATCH_CONFIG,
        extract=extract_config,
        uri="tmp_writer/",
        target_aoi=POLYGON,
        cells_per_task=2,
    )

    runner = TaskRunner()
    for task in tasks:
        artifacts = runner.run(task)
        print(f"Writer: wrote {len(artifacts)} artifacts for task")


# ---------------------------------------------------------------------------
# 2b. Extract with BatchWriter (memory-controlled approach)
# ---------------------------------------------------------------------------


def extract_with_batch_writer():
    """Batch approach: BatchWriteGeoTIFF receives the full patch map.

    Benefits:
    - Can batch ``.compute()`` calls across multiple patches (Dask-aware).
    - Explicitly drops each patch from memory immediately after writing.
    - Full control over iteration order and parallelism within a task.
    """
    from aereo.read_satpy import ReadSatpy
    from aereo.reproject_satpy import ReprojectSatpy

    reader = ReadSatpy(wishlist=["I04"], reader="viirs_l1b")
    reprojector = ReprojectSatpy()
    writer = BatchWriteGeoTIFF()  # <-- BatchWriter instead of Writer

    extract_config = ExtractConfig(
        read=reader,
        reproject=reprojector,
        write=writer,
    )

    tasks = prepare_for_extraction(
        search_results=assets,
        grid_config=GRID_CONFIG,
        patch_config=PATCH_CONFIG,
        extract=extract_config,
        uri="tmp_batch_writer/",
        target_aoi=POLYGON,
        cells_per_task=2,
    )

    runner = TaskRunner()
    for task in tasks:
        artifacts = runner.run(task)
        print(f"BatchWriter: wrote {len(artifacts)} artifacts for task")


# ---------------------------------------------------------------------------
# 2c. Full pipeline via AereoClient (recommended)
# ---------------------------------------------------------------------------


def extract_with_client():
    """Use AereoClient for search → prepare → extract with BatchWriter."""
    from aereo.read_satpy import ReadSatpy
    from aereo.reproject_satpy import ReprojectSatpy

    client = AereoClient()

    # Search
    search = SearchEarthaccess(
        collections={"VJ202IMG": ["I04"], "VJ203IMG": []},
        intersects=POLYGON,
        start_datetime=START,
        end_datetime=END,
    )
    assets = client.search(search)
    print(f"Client search: found {len(assets)} assets")

    # Prepare
    reader = ReadSatpy(wishlist=["I04"], reader="viirs_l1b")
    reprojector = ReprojectSatpy()
    writer = BatchWriteGeoTIFF()

    extract_config = ExtractConfig(
        read=reader,
        reproject=reprojector,
        write=writer,
    )

    tasks = client.prepare_tasks(
        search_results=assets,
        grid_config=GRID_CONFIG,
        patch_config=PATCH_CONFIG,
        extract=extract_config,
        uri="tmp_client/",
        cells_per_task=2,
    )
    print(f"Client prepared: {len(tasks)} tasks")

    # Extract with parallel backend
    backend = LocalProcessBackend(max_workers=2)
    artifacts = client.execute_tasks(tasks, backend=backend)
    print(f"Client extract: {len(artifacts)} total artifacts")


# ---------------------------------------------------------------------------
# 3. Manual inspection (as in the original snippet)
# ---------------------------------------------------------------------------


def manual_inspection():
    """Manually read and reproject a single task for debugging."""
    from aereo.read_satpy import ReadSatpy
    from aereo.reproject_satpy import ReprojectSatpy

    reader = ReadSatpy(wishlist=["I04"], reader="viirs_l1b")
    reprojector = ReprojectSatpy()

    extract_config = ExtractConfig(read=reader)

    tasks = prepare_for_extraction(
        search_results=assets,
        grid_config=GRID_CONFIG,
        patch_config=PATCH_CONFIG,
        extract=extract_config,
        uri="tmp_manual/",
        target_aoi=POLYGON,
        cells_per_task=2,
    )

    task = tasks[0]
    ds = reader(task)
    resampled_ds = reprojector(ds, task)

    print(f"Manual: task has {len(task.patches)} patches")
    print(f"Manual: reprojected_map keys = {list(resampled_ds.keys())}")
    for patch_id, patch_ds in resampled_ds.items():
        print(f"  {patch_id}: {patch_ds.dims}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Uncomment the approach you want to run:

    # extract_with_writer()
    extract_with_batch_writer()
    # extract_with_client()
    # manual_inspection()
