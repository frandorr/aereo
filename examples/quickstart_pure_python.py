"""Pure-Python quickstart for AEREO.

This example builds an ``ExtractionJob`` and runs the search → build-tasks →
extract pipeline without any YAML config files or Hydra. It is the fastest way
to see the function-based AEREO API in action.

The example uses a tiny AOI so it can run quickly. Set ``DRY_RUN=true`` to
validate the job without making network calls:

    DRY_RUN=true uv run python examples/quickstart_pure_python.py

To run the full pipeline:

    uv run python examples/quickstart_pure_python.py
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from shapely.geometry import Polygon

from aereo.builtins import (
    build_grouped_tasks,
    read_odc_stac,
    search_stac,
    write_geotiff,
)
from aereo.executors import LocalExecutor
from aereo.interfaces import PatchConfig
from aereo.pipeline import ExtractionJob

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")


def main() -> None:
    """Build a job in pure Python and run the extraction pipeline."""
    # Tiny AOI around Chocón reservoir, Argentina.
    aoi = Polygon(
        [
            (-68.90986824592407, -39.23705421799603),
            (-68.65925870907353, -39.23705421799603),
            (-68.65925870907353, -39.41589522092947),
            (-68.90986824592407, -39.41589522092947),
            (-68.90986824592407, -39.23705421799603),
        ]
    )

    patch_config = PatchConfig(
        resolution=10.0,
        padding=0,
        margin=10.0,
        conform_to=None,
    )

    job = ExtractionJob(
        name="quickstart",
        grid_dist=10_000,
        output_uri="/tmp/aereo_quickstart",
        read=read_odc_stac,
        write=write_geotiff,
        target_aoi=aoi,
    )

    print("--- ExtractionJob ---")
    print(f"name: {job.name}")
    print(f"output_uri: {job.output_uri}")
    print(f"grid_dist: {job.grid_dist}")
    print(f"patch_config.resolution: {patch_config.resolution}")

    if DRY_RUN:
        print("\nDRY_RUN enabled: skipping search/build-tasks/extract.")
        return

    print("\n--- Search ---")
    assets = job.search(
        search_stac,
        stac_api_url="https://earth-search.aws.element84.com/v1",
        collections={"sentinel-2-l2a": ["red", "nir"]},
        intersects=aoi,
        start_datetime=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_datetime=datetime(2024, 1, 10, tzinfo=timezone.utc),
    )
    print(f"Found {len(assets)} asset rows")

    if assets.empty:
        print("No assets found; nothing to extract.")
        return

    print("\n--- Build tasks ---")
    tasks = job.build_tasks(
        assets, build_grouped_tasks, patch_config=patch_config, cells_per_task=5
    )
    print(f"Built {len(tasks)} task(s)")

    print("\n--- Extract ---")
    artifacts = job.execute(tasks, executor=LocalExecutor(workers=1))
    print(f"Extracted {len(artifacts)} artifact(s)")

    catalog_uri = job.write_catalog(artifacts)
    print(f"\nCatalog written to: {catalog_uri}")


if __name__ == "__main__":
    main()
