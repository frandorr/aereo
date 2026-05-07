"""
Buenos Aires Sentinel-2 Planetary Computer Search & Extraction Example

This script demonstrates:
1. Searching Sentinel-2 L2A data via aer-search-planetary-computer
2. Extracting RGB imagery via aer-extract-odc-stac
3. Visualizing a single grid cell as PNG

Uses a small AOI around Buenos Aires city center with 10km grid cells.
"""

from datetime import datetime, timezone
from pathlib import Path
import shutil

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.plot import show

from aer.client import AerClient
from aer.interfaces import ExtractionProfile


def main():
    # --- Configuration ---
    DATE_START = datetime(2025, 4, 1, 0, 0, tzinfo=timezone.utc)
    DATE_END = datetime(2025, 4, 7, 0, 0, tzinfo=timezone.utc)

    # Load AOI (small area around Buenos Aires city center)
    geojson_path = Path("../buenos_aires_city.geojson")
    gdf = gpd.read_file(geojson_path)
    aoi = gdf.geometry.iloc[0]

    # --- Client Setup ---
    client = AerClient()

    print("Searching Sentinel-2 L2A on Planetary Computer...", flush=True)
    results = client.search(
        collections=["sentinel-2-l2a"],
        start_datetime=DATE_START,
        end_datetime=DATE_END,
        intersects=aoi,
    )
    print(f"Found {len(results)} asset rows", flush=True)
    print(results[["id", "collection", "channel_id", "start_time"]].head(10))

    # --- Prepare Extraction ---
    uri = "extract_buenos_aires_sentinel2_pc"

    profiles = [
        ExtractionProfile(
            name="s2_rgb",
            resolution=100,
            collection_variables_map={"sentinel-2-l2a": ["B04", "B03", "B02"]},
        )
    ]

    # Clean output directory
    uri_path = Path(uri)
    if uri_path.exists():
        shutil.rmtree(uri_path)
    uri_path.mkdir(parents=True, exist_ok=True)

    tasks = client.prepare_for_extraction(
        results,
        target_aoi=aoi,
        uri=uri,
        profiles=profiles,
        target_grid_dist=10_000,  # 10km grid cells
        target_grid_overlap=False,
        prepare_params={"cells_per_chunk": 5},
    )

    print(f"Prepared {len(tasks)} extraction tasks", flush=True)
    for i, t in enumerate(tasks):
        print(f"  Task {i}: {len(t.grid_cells)} grid cells")

    # --- Extract ---
    print("Extracting...", flush=True)
    results_df = client.extract_batches(
        tasks,
        max_batch_workers=2,
    )

    print(f"Extracted {len(results_df)} artifacts", flush=True)
    if len(results_df) > 0:
        print(results_df[["id", "collection", "grid_cell", "uri"]].head())

        # --- Visualize a single grid cell ---
        first_artifact = results_df.iloc[0]
        raster_path = first_artifact["uri"]
        grid_cell_id = first_artifact["grid_cell"]

        print(f"Visualizing grid cell {grid_cell_id} from {raster_path}", flush=True)

        fig, ax = plt.subplots(figsize=(8, 8))
        with rasterio.open(raster_path) as src:
            # Read RGB bands (assuming B04=red, B03=green, B02=blue)
            # For visualization, scale to 0-1 range
            red = src.read(1)
            green = src.read(1) if src.count > 1 else red
            blue = src.read(1) if src.count > 1 else red

            # Simple percentile stretch
            from numpy import percentile

            rgb = np.stack([red, green, blue], axis=0)
            vmin = percentile(rgb, 2)
            vmax = percentile(rgb, 98)
            rgb = np.clip((rgb - vmin) / (vmax - vmin + 1e-9), 0, 1)

            show(rgb, ax=ax, transform=src.transform)

        ax.set_title(f"Sentinel-2 L2A RGB\nGrid cell: {grid_cell_id}")
        ax.axis("off")

        png_path = Path(uri) / f"visualization_{grid_cell_id}.png"
        plt.tight_layout()
        plt.savefig(png_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Saved visualization to {png_path}", flush=True)
    else:
        print("No artifacts extracted - nothing to visualize", flush=True)


if __name__ == "__main__":
    main()
