#!/usr/bin/env python
"""Extract visible-band reflectance data for Neuquén across 4 constellations."""

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd

from aer.client import AerClient
from aer.interfaces import ExtractionProfile
from aer.search_earthaccess import earthaccess_download_wrapper


def extract_constellation(
    name,
    collections,
    band,
    resolution,
    reader,
    date_start,
    date_end,
    uri,
    extra_search_params=None,
    extra_extract_params=None,
    search_hints=None,
    extract_hints=None,
    satellite=None,
):
    print(f"\n{'=' * 60}")
    print(f"=== {name} ===")
    print(f"{'=' * 60}")

    geojson_path = Path("neuquen_city.geojson")
    gdf = gpd.read_file(geojson_path)
    aoi = gdf.geometry.iloc[0]

    client = AerClient()

    print(f"Searching {collections} from {date_start} to {date_end}...")
    results = client.search(
        collections=collections,
        start_datetime=date_start,
        end_datetime=date_end,
        intersects=aoi,
        search_params=extra_search_params or {},
        plugin_hints=search_hints or {},
    )
    print(f"Found {len(results)} results")
    if len(results) == 0:
        print("WARNING: No results found!")
        return None

    profiles = [
        ExtractionProfile(
            name=f"{name.lower().replace(' ', '_')}_vis",
            resolution=resolution,
            collection_variables_map={
                c: [band] if i == 0 else [] for i, c in enumerate(collections)
            },
            reader=reader,
            padding=2,
            resampling="nearest",
            calibration="reflectance",
            satellite=satellite,
        )
    ]

    tasks = client.prepare_for_extraction(
        results,
        target_aoi=aoi,
        uri=uri,
        profiles=profiles,
        target_grid_dist=256000,
        target_grid_overlap=False,
        prepare_params={"cells_per_chunk": 10},
    )
    print(f"Prepared {len(tasks)} tasks")

    uri_path = Path(uri)
    if uri_path.exists():
        shutil.rmtree(uri_path)
    uri_path.mkdir(parents=True)

    # extract_params is reserved for meta-level / tool-level parameters.
    # Domain-specific config (padding, calibration, reader, etc.) lives on the profile.
    extract_params = dict(extra_extract_params) if extra_extract_params else {}

    print("Extracting...")
    start = time.time()
    results_df = client.extract_batches(
        tasks,
        extract_params=extract_params,
        plugin_hints=extract_hints or {},
        max_batch_workers=None,  # sequential to avoid BrokenProcessPool
    )
    elapsed = time.time() - start
    print(f"{name} extracted {len(results_df)} artifacts in {elapsed:.1f}s")
    return results_df


def main():
    # GOES-19 ABI (public S3, no downloader needed)
    extract_constellation(
        name="GOES-19 ABI",
        collections=["ABI-L1b-RadF"],
        band="C02",
        resolution=2000,
        reader="abi_l1b",
        date_start=datetime(2025, 12, 15, 15, 0, tzinfo=timezone.utc),
        date_end=datetime(2025, 12, 15, 15, 10, tzinfo=timezone.utc),
        uri="extraction/extract_neuquen_goes",
        extra_search_params={"ABI-L1b-RadF": {"satellite": "GOES-19"}},
        search_hints={"search_aws_goes": ["ABI-L1b-RadF"]},
        extract_hints={"extract_satpy": ["ABI-L1b-RadF"]},
    )

    # MODIS Terra
    extract_constellation(
        name="MODIS Terra",
        collections=["MOD021KM"],
        band="1",
        resolution=1000,
        reader="modis_l1b",
        date_start=datetime(2025, 12, 10, 0, 0, tzinfo=timezone.utc),
        date_end=datetime(2025, 12, 20, 0, 0, tzinfo=timezone.utc),
        uri="extraction/extract_neuquen_modis",
        extra_extract_params={"downloader": earthaccess_download_wrapper},
        search_hints={"search_earthaccess": ["MOD021KM"]},
        extract_hints={"extract_satpy": ["MOD021KM"]},
    )

    # VIIRS NOAA-21
    extract_constellation(
        name="VIIRS NOAA-21",
        collections=["VJ202IMG", "VJ203IMG"],
        band="I01",
        resolution=400,
        reader="viirs_l1b",
        satellite="NOAA21",
        date_start=datetime(2025, 12, 10, 0, 0, tzinfo=timezone.utc),
        date_end=datetime(2025, 12, 20, 0, 0, tzinfo=timezone.utc),
        uri="extraction/extract_neuquen_viirs",
        extra_extract_params={
            "downloader": earthaccess_download_wrapper,
        },
        search_hints={"search_earthaccess": ["VJ202IMG", "VJ203IMG"]},
        extract_hints={"extract_satpy": ["VJ202IMG", "VJ203IMG"]},
    )

    # Sentinel-3 OLCI
    extract_constellation(
        name="Sentinel-3 OLCI",
        collections=["S3A_OL_1_EFR"],
        band="Oa08",
        resolution=300,
        reader="olci_l1b",
        date_start=datetime(2025, 12, 10, 0, 0, tzinfo=timezone.utc),
        date_end=datetime(2025, 12, 20, 0, 0, tzinfo=timezone.utc),
        uri="extraction/extract_neuquen_sentinel3",
        extra_extract_params={"downloader": earthaccess_download_wrapper},
        search_hints={"search_earthaccess": ["S3A_OL_1_EFR"]},
        extract_hints={"extract_satpy": ["S3A_OL_1_EFR"]},
    )

    print("\nAll extractions complete!")


if __name__ == "__main__":
    main()
