#!/usr/bin/env python3
"""Integration test for GOES ABI extraction via aws-goes search + satpy."""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import time

import geopandas as gpd

from aer.client import AerClient
from aer.interfaces import ExtractionProfile


def main() -> None:
    # --- Configuration ---
    BAND = "C07"  # GOES ABI band (C01-C16 for L1b)
    DATE_START = datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc)
    DATE_END = datetime(2026, 4, 1, 15, 10, tzinfo=timezone.utc)

    # Load AOI
    geojson_path = Path(__file__).parent / "cordoba.geojson"
    gdf = gpd.read_file(geojson_path)
    aoi = gdf.geometry.iloc[0]

    # --- Client Setup ---
    client = AerClient()

    # --- Search using aws-goes ---
    collections = ["ABI-L1b-RadF"]

    print("Searching...", flush=True)
    results = client.search(
        collections=collections,
        start_datetime=DATE_START,
        end_datetime=DATE_END,
        intersects=aoi,
        search_params={"ABI-L1b-RadF": {"satellite": "GOES-19"}},
        plugin_hints={"search_aws_goes": collections},
    )

    print(f"Found {len(results)} results", flush=True)
    if len(results) == 0:
        print("No results found — test cannot proceed.")
        exit(1)

    # --- Prepare Extraction ---
    uri = "extract_test_goes_satpy"

    profiles = [
        ExtractionProfile(
            name="goes_band",
            resolution=2000,
            collection_variables_map={"ABI-L1b-RadF": [BAND]},
            extra_params={"reader": "abi_l1b"},
        )
    ]

    prepare_params = {
        "cells_per_chunk": 10,
    }

    tasks = client.prepare_for_extraction(
        results,
        target_aoi=aoi,
        uri=uri,
        profiles=profiles,
        target_grid_dist=256000,
        target_grid_overlap=False,
        prepare_params=prepare_params,
        plugin_hints={"extract_satpy": collections},
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
        "padding": 0,
        "resampling": "nearest",
        "calibration": "radiance",
    }

    results_df = client.extract_batches(
        tasks,
        extract_params=extract_params,
        plugin_hints={"extract_satpy": collections},
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
