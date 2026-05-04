#!/usr/bin/env python3
"""Integration test for MODIS L1B extraction via earthaccess + satpy."""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import time

import geopandas as gpd

from aer.client import AerClient
from aer.interfaces import ExtractionProfile
from aer.search_earthaccess import earthaccess_download_wrapper


def main() -> None:
    # --- Configuration ---
    DATE_START = datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc)
    DATE_END = datetime(2026, 4, 1, 15, 30, tzinfo=timezone.utc)

    # Load AOI
    geojson_path = Path(__file__).parent / "cordoba.geojson"
    gdf = gpd.read_file(geojson_path)
    aoi = gdf.geometry.iloc[0]

    # --- Client Setup ---
    client = AerClient()

    # --- Search using earthaccess ---
    collections = ["MOD021KM", "MYD021KM"]  # Terra and Aqua L1B 1km

    print("Searching...", flush=True)
    results = client.search(
        collections=collections,
        start_datetime=DATE_START,
        end_datetime=DATE_END,
        intersects=aoi,
        plugin_hints={"search_earthaccess": collections},
    )

    print(f"Found {len(results)} results", flush=True)
    if len(results) == 0:
        print("No results found — test cannot proceed.")
        exit(1)

    # --- Prepare Extraction ---
    uri = "extract_test_modis"

    profiles = [
        ExtractionProfile(
            name="modis_thermal",
            resolution=1000,
            collection_variables_map={"MOD021KM": ["31"], "MYD021KM": ["31"]},
            extra_params={"reader": "modis_l1b"},
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
        "downloader": earthaccess_download_wrapper,
        "calibration": "brightness_temperature",
        "padding": 2,
        "resampler": "nearest",
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
