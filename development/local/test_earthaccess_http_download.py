#!/usr/bin/env python3
"""Integration test for earthaccess HTTP download via Downloader Protocol."""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import time

import earthaccess
import geopandas as gpd

from aer.client import AerClient
from aer.interfaces import ExtractionProfile
from aer.search_earthaccess import earthaccess_downloader


# --- Configuration ---
DATE_START = datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc)
DATE_END = datetime(2026, 4, 2, 15, 2, tzinfo=timezone.utc)


def main() -> None:
    # Load AOI
    bari_path = Path(__file__).parent / "bari.geojson"
    gdf = gpd.read_file(bari_path)
    aoi = gdf.geometry.iloc[0]

    # Authenticate with Earthdata
    earthaccess.login()

    # --- Client Setup ---
    client = AerClient()

    # --- Search using earthaccess ---
    print("Searching...", flush=True)
    results = client.search(
        collections=["VJ202IMG", "VJ203IMG"],
        start_datetime=DATE_START,
        end_datetime=DATE_END,
        intersects=aoi,
        plugin_hints={
            "VJ202IMG": "search_earthaccess",
            "VJ203IMG": "search_earthaccess",
        },
    )

    print(f"Found {len(results)} results", flush=True)
    if len(results) == 0:
        print("No results found — test cannot proceed.")
        exit(1)

    # Verify new columns exist
    assert "s3_url" in results.columns, "Missing s3_url column"
    assert "https_url" in results.columns, "Missing https_url column"
    print(f"Columns: {list(results.columns)}", flush=True)
    print(f"Sample s3_url: {results['s3_url'].iloc[0]}", flush=True)
    print(f"Sample https_url: {results['https_url'].iloc[0]}", flush=True)

    # --- Prepare Extraction ---
    uri = "extract_test_viirs_http"

    profiles = [
        ExtractionProfile(
            name="viirs_i4",
            resolution=400,
            collection_variables_map={"VJ202IMG": ["I04"]},
        )
    ]

    tasks = client.prepare_for_extraction(
        results,
        target_aoi=aoi,
        uri=uri,
        profiles=profiles,
        init_params={"target_grid_d": 100_000, "target_grid_overlap": False},
        prepare_params={"cells_per_chunk": 10},
        plugin_hints={"VJ202IMG": "extract_satpy", "VJ203IMG": "extract_satpy"},
    )

    print(f"Prepared {len(tasks)} extraction tasks", flush=True)
    if len(tasks) == 0:
        print("No tasks prepared — test cannot proceed.")
        exit(1)

    # --- Clean and Extract ---
    uri_path = Path(uri)
    if uri_path.exists():
        shutil.rmtree(uri_path)
    uri_path.mkdir(parents=True)

    print("Extracting...", flush=True)
    start_time = time.time()

    extract_params = {
        "padding": 2,
        "resampling": "nearest",
        "calibration": "radiance",
        "satellite": "NOAA21",
        "downloader": earthaccess_downloader,
    }

    results_df = client.extract_batches(
        tasks,
        extract_params=extract_params,
        plugin_hints={"VJ202IMG": "extract_satpy", "VJ203IMG": "extract_satpy"},
        max_batch_workers=1,  # keep it simple for the test
    )

    end_time = time.time()
    print(f"Extraction took {end_time - start_time:.2f}s")
    print(f"Extracted {len(results_df)} artifacts")

    # --- Show results ---
    if len(results_df) > 0:
        print(results_df[["id", "collection", "grid_cell", "uri"]].head())
        print("TEST PASSED")
    else:
        print("TEST FAILED: no artifacts extracted")
        exit(1)


if __name__ == "__main__":
    main()
