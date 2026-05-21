# %%
# 06_geotessera_zarr.py
# GeoTessera Zarr embedding extraction: stream Tessera embeddings directly
# from cloud-native Zarr storage into grid-aligned GeoTIFFs.
#
# Tessera embeddings are *global annual composites* — the search plugin
# generates synthetic availability assets (one per year), so there is no
# STAC catalog query.
#
# Plugins used:
#   - aer-search-geotessera-zarr  (search provider)
#   - aer-extract-geotessera-zarr (extractor)
#
# Common pitfalls:
#   1. Ensure `geotessera` is installed (`uv pip install geotessera`).
#   2. Uses a small 5 km grid to keep per-cell memory manageable
#      (128 bands × 500×500 px at 10 m ≈ 130 MB).
#   3. Unlike imagery profiles, the collection has no "variables" —
#      use an empty list (`geotessera-zarr: []`).
#   4. Cells near UTM zone boundaries are read from the *dominant zone*
#      only — a warning is logged if this occurs.

from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio

from aer.client import AerClient, FailureMode
from aer.eoids import scan_eoids_dir
from aer.interfaces import AerProfile, GridConfig

# --- Configuration ---
# Tessera covers 2017–2025. Pick a single year to keep the example fast.
DATE_START = datetime(2023, 1, 1, tzinfo=timezone.utc)
DATE_END = datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
URI = "/tmp/06_geotessera_zarr_extraction"

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
# Embeddings use a smaller 5 km grid to keep per-cell memory manageable.
all_profiles = {p.name: p for p in AerProfile.from_yaml(data_dir / "profiles.yaml")}
grid = GridConfig.from_yaml(data_dir / "grid_config_embeddings.yaml")

profile = all_profiles["tessera_zarr_emb"]
profiles = [profile]

# --- Client Setup ---
client = AerClient()

print(f"\n{'=' * 60}")
print("  Processing: tessera_zarr_emb")
print(f"{'=' * 60}")

# Step 1: Search
print("Searching...", flush=True)
results = client.search(
    profiles=profiles,
    start_datetime=DATE_START,
    end_datetime=DATE_END,
    intersects=aoi,
)
print(results[["collection", "start_time", "end_time"]].to_string())

# %%
# Step 2: Prepare extraction tasks.
# cells_per_chunk=1 keeps memory usage low for embedding data.
tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    grid_config=grid,
    target_aoi=aoi,
    uri=URI,
    profiles=profiles,
    cells_per_chunk=1,
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)

# For the smoke test we keep a few tasks.
# Grid cells are sorted spatially; we sample from the middle.
mid = len(tasks) // 2
tasks = tasks[mid : mid + 3]
print(f"Extracting {len(tasks)} task(s)...", flush=True)

# Step 3: Extract
# Use BEST_EFFORT so cells with no tile coverage don't abort the run.
results_df = client.extract_batches(
    tasks,
    max_batch_workers=None,  # sequential — safe for first runs
    failure_mode=FailureMode.BEST_EFFORT,
)
print(f"Extracted {len(results_df)} artifacts")

# %%
# --- Verify and inspect artifacts ---
entries = scan_eoids_dir(URI)
print(f"\nDiscovered {len(entries)} artifacts on disk:")
for e in entries:
    print(f"  {e['path'].name}  (collection={e['collection']})")

# %%
# --- Visualize embedding dimensions ---
# Each artifact is a 128-band GeoTIFF where each band is one embedding
# dimension. We show the first 8 dimensions as a heatmap grid.

DIMS_TO_SHOW = 8

if not entries:
    print("No artifacts found — skipping visualization.")
else:
    fig, axes = plt.subplots(
        1,
        DIMS_TO_SHOW,
        figsize=(2.5 * DIMS_TO_SHOW, 3),
        squeeze=False,
    )
    fig.suptitle(
        "Tessera Zarr Embedding Dimensions – Chocon AOI (2023)",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )

    artifact_path = entries[0]["path"]
    with rasterio.open(artifact_path) as src:
        data = src.read()  # (bands, H, W)
        n_bands = src.count
        print(f"  {src.shape} pixels, {n_bands} bands")

    for dim in range(min(DIMS_TO_SHOW, n_bands)):
        ax = axes[0, dim]
        band = data[dim].astype(np.float32)

        valid = band[np.isfinite(band) & (band != 0)]
        if len(valid) > 0:
            vmin, vmax = np.percentile(valid, [2, 98])
        else:
            vmin, vmax = 0, 1

        im = ax.imshow(band, cmap="viridis", vmin=vmin, vmax=vmax)
        ax.set_title(f"Dim {dim}", fontsize=9)
        ax.axis("off")

    for dim in range(min(DIMS_TO_SHOW, n_bands), DIMS_TO_SHOW):
        axes[0, dim].axis("off")

    fig.colorbar(im, ax=axes, shrink=0.6, label="Embedding value", pad=0.02)
    plt.tight_layout()
    plt.savefig("/tmp/06_geotessera_zarr.png", dpi=150, bbox_inches="tight")
    print("\nSaved visualization to /tmp/06_geotessera_zarr.png")

# %%
# --- Summary statistics ---
print("\n--- Embedding Statistics ---")
for entry in entries:
    with rasterio.open(entry["path"]) as src:
        data = src.read().astype(np.float32)
        valid = data[np.isfinite(data) & (data != 0)]
        print(f"  {entry['path'].name}")
        print(f"    Bands: {src.count}")
        print(f"    Shape: {src.shape}")
        print(f"    CRS:   {src.crs}")
        if len(valid) > 0:
            print(f"    Mean:  {valid.mean():.4f}")
            print(f"    Std:   {valid.std():.4f}")
            print(f"    Range: [{valid.min():.4f}, {valid.max():.4f}]")
        else:
            print("    No valid data (all nodata)")
