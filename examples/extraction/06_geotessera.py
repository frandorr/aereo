# ruff: noqa: E402
# %%
# 06_geotessera.py
# GeoTessera embedding extraction: search → extract → visualize embedding bands.
#
# This example demonstrates the full pipeline for GeoTessera satellite
# embeddings using the aereo-search-tessera and aereo-extract-tessera plugins.
#
# Plugins used:
#   - aereo-search-tessera  (search provider)
#   - aereo-extract-tessera (extractor)
#
# The GeoTessera dataset provides 128-dimensional embedding tensors
# (shape H×W×128) stored as remote .npy files. The extractor downloads
# tiles in parallel, lazily reprojects them to the target grid, mosaics
# overlapping coverage, and writes multi-band GeoTIFFs.

import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from aereo.backends import LocalProcessBackend
from aereo.client import AereoClient
from aereo.eoids import scan_eoids_dir
from aereo.interfaces import AereoProfile, GridConfig
from examples.helpers.eoids_mosaic import mosaic_eoids_tiles
from pyproj import Transformer
from shapely.ops import transform as shapely_transform

# --- Configuration ---
# GeoTessera covers 2017–2025. We use 2024 which has coverage for the Chocon AOI.
DATE_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DATE_END = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
URI = "/root/repos/aereo/examples/extraction/06_geotessera_extraction_output"

# Shared AOI — path relative to this script so it works regardless of CWD
try:
    data_dir = Path(__file__).parent / ".." / "data"
except NameError:
    data_dir = Path().resolve() / "examples" / "data"

geojson_path = data_dir / "chocon.geojson"
gdf = gpd.read_file(geojson_path)
aoi = gdf.geometry.iloc[0]

# %%
# Load shared profiles and grid config from YAML.
all_profiles = {p.name: p for p in AereoProfile.from_yaml(data_dir / "profiles.yaml")}
grid = GridConfig.from_yaml(data_dir / "grid_config.yaml")

profiles = [all_profiles["geotessera"]]

# --- Client Setup ---
# cells_per_task=4 keeps the example fast and memory-light.
client = AereoClient(
    profiles=profiles,
    grid_config=grid,
    aoi=aoi,
    backend=LocalProcessBackend(max_workers=8),
    cells_per_task=2,
)

print("Searching GeoTessera tiles...", flush=True)
t0 = time.time()
results = client.search(
    start_datetime=DATE_START,
    end_datetime=DATE_END,
)
print(f"Search completed in {time.time() - t0:.2f}s")
print(
    results[
        ["collection", "start_time", "end_time", "tile_lon", "tile_lat"]
    ].to_string()
)

# %%
# Prepare extraction tasks using the same profiles.
tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    uri=URI,
)

print(f"Prepared {len(tasks)} extraction task(s)", flush=True)

# %%
# Extract embedding tensors.
# max_download_workers controls the ThreadPoolExecutor for .npy downloads.
print(f"Extracting {len(tasks)} task(s)...", flush=True)
start_time = time.time()
results_df = client.execute_tasks(tasks)
print(f"Extraction completed in {time.time() - start_time:.2f}s")
print(f"Extracted {len(results_df)} artifacts")

# %%
# --- Mosaic & plot embedding bands ---
# Discover unique collections that were actually extracted
entries = scan_eoids_dir(URI)
collections = sorted({e["collection"] for e in entries})
print(f"Collections to mosaic: {collections}")

# Verify the artifact is a multi-band GeoTIFF
artifact_paths = [e["path"] for e in entries if e.get("profile") == "geotessera"]
if artifact_paths:
    with rasterio.open(artifact_paths[0]) as src:
        print(f"Verified artifact: {artifact_paths[0].name}")
        print(f"  Bands: {src.count} (extracting dims 0,1,2 for demo speed)")
        print(f"  Shape: {src.shape}")
        print(f"  CRS:   {src.crs}")

# Mosaic extracted tiles. We set sort_by_coverage=False because GeoTessera
# tiles are dense rectangles — the coverage sort would read every tile into
# memory just to count pixels, which is very slow for many dense tiles.
# target_resolution=0.001 (~111 m in degrees) keeps the preview fast while
# still looking sharp on an 8" plot at 150 dpi.
mosaic, transform, crs = mosaic_eoids_tiles(
    URI,
    profile=profiles[0].name,
    sort_by_coverage=False,
    target_resolution=0.001,
)

print(f"Mosaic shape: {mosaic.shape} (bands, height, width)")

# %%
# Visualize three embedding dimensions as a false-color RGB composite.
# Bands 1, 2, 3 correspond to embedding dimensions 0, 1, 2.
if mosaic.shape[0] >= 3:
    rgb = mosaic[:3].transpose(1, 2, 0).astype(np.float32)  # (3, H, W) -> (H, W, 3)

    # Mask invalid pixels (nodata = 0, NaN)
    valid_mask = np.all((rgb != 0) & np.isfinite(rgb), axis=-1)
    if valid_mask.any():
        valid_pixels = rgb[valid_mask]
        # Percentile stretch per band for visualization
        vmin, vmax = np.percentile(valid_pixels, [2, 98])
        rgb = np.clip((rgb - vmin) / (vmax - vmin + 1e-8), 0, 1)
    else:
        print("Warning: no valid pixels found for RGB composite")

    fig, ax = plt.subplots(figsize=(8, 6))
    extent = (
        transform.c,
        transform.c + transform.a * rgb.shape[1],
        transform.f + transform.e * rgb.shape[0],
        transform.f,
    )
    ax.imshow(rgb, extent=extent)

    # Reproject AOI boundary to mosaic CRS and overlay it
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    aoi_projected = shapely_transform(transformer.transform, aoi)
    xs, ys = aoi_projected.exterior.xy
    ax.plot(xs, ys, color="red", linewidth=2, label="AOI boundary")

    ax.legend(loc="upper right")
    ax.set_title("GeoTessera Embedding RGB (dims 0, 1, 2) @ ~111 m")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    plt.tight_layout()
    plt.savefig(
        "/root/repos/aereo/examples/extraction/06_geotessera_extraction_output/06_geotessera_rgb.png",
        dpi=150,
    )
    print(
        "Saved RGB mosaic to /root/repos/aereo/examples/extraction/06_geotessera_extraction_output/06_geotessera_rgb.png"
    )

# %%
# Also visualize a single embedding dimension (band 1 = dim 0) with a colormap.
fig, ax = plt.subplots(figsize=(8, 6))
band = mosaic[0]
valid = band[(band != 0) & np.isfinite(band)]
if valid.size > 0:
    vmin, vmax = np.percentile(valid, [2, 98])
    extent = (
        transform.c,
        transform.c + transform.a * mosaic.shape[2],
        transform.f + transform.e * mosaic.shape[1],
        transform.f,
    )
    im = ax.imshow(band, extent=extent, vmin=vmin, vmax=vmax, cmap="viridis")
    fig.colorbar(im, ax=ax, shrink=0.6, label="Embedding dim 0 (arbitrary units)")

    # Reproject AOI boundary to mosaic CRS and overlay it
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    aoi_projected = shapely_transform(transformer.transform, aoi)
    xs, ys = aoi_projected.exterior.xy
    ax.plot(xs, ys, color="red", linewidth=2, label="AOI boundary")

    ax.legend(loc="upper right")
    ax.set_title("GeoTessera Embedding Dim 0 @ ~111 m")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    plt.tight_layout()
    plt.savefig(
        "/root/repos/aereo/examples/extraction/06_geotessera_extraction_output/06_geotessera_single_band.png",
        dpi=150,
    )
    print(
        "Saved single-band mosaic to /root/repos/aereo/examples/extraction/06_geotessera_extraction_output/06_geotessera_single_band.png"
    )
else:
    print("Warning: no valid pixels found for single-band visualization")
