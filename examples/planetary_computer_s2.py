"""Pure-Python quickstart using Planetary Computer's Sentinel-2 L2A.

Requires the optional ``planetary-computer`` dependency:

    uv add --optional pc planetary-computer
    # or
    pip install 'aereo[pc]'

To run the full pipeline:

    uv run python examples/planetary_computer_s2.py

The example uses the Microsoft Planetary Computer STAC API, which serves
globally-corrected Sentinel-2 L2A data as Cloud Optimized GeoTIFFs via Azure
Blob Storage. ``planetary_computer.sign_inplace`` is used during search so
asset hrefs are already signed, and ``planetary_computer.sign`` is passed to
``read_odc_stac`` as ``patch_url`` to sign any remaining URLs at load time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import partial

import planetary_computer
from shapely.geometry import Polygon

from aereo.builtins import (
    build_grouped_tasks,
    read_odc_stac,
    search_stac,
    write_geotiff,
)
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob


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

    job = ExtractionJob(
        name="pc_s2_demo",
        grid_dist=10_000,
        output_uri="/tmp/aereo_pc_s2_demo",
        search=search_stac,
        read=partial(
            read_odc_stac,
            patch_url=planetary_computer.sign,
            dtype="uint16",
            nodata=0,
        ),
        write=write_geotiff,
        target_aoi=aoi,
    )

    print("--- ExtractionJob ---")
    print(f"name: {job.name}")
    print(f"output_uri: {job.output_uri}")
    print(f"grid_dist: {job.grid_dist}")

    print("\n--- Search ---")
    assets = job.search(
        stac_api_url="https://planetarycomputer.microsoft.com/api/stac/v1",
        collections={"sentinel-2-l2a": ["B04", "B08"]},
        intersects=aoi,
        start_datetime=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_datetime=datetime(2024, 1, 3, tzinfo=timezone.utc),
        pystac_open_params={"modifier": planetary_computer.sign_inplace},
    )
    print(f"Found {len(assets)} asset rows")

    if assets.empty:
        print("No assets found; nothing to extract.")
        return

    print("\n--- Build tasks ---")
    tasks = job.build_tasks(assets, build_grouped_tasks)
    print(f"Built {len(tasks)} task(s)")

    print("\n--- Extract ---")
    artifacts = job.execute(
        tasks,
        executor=LocalExecutor(workers=-1, use_threads=True),
    )
    print(f"Extracted {len(artifacts)} artifact(s)")

    catalog_uri = job.write_catalog(artifacts)
    print(f"\nCatalog written to: {catalog_uri}")


if __name__ == "__main__":
    main()
