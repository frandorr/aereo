# ruff: noqa: E402
# %%
# 03_sentinel2_msi.py
# Sentinel-2 MSI via Planetary Computer: search → extract → true-color RGB composite.


from datetime import datetime, timezone
from pathlib import Path
import time

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer
import rasterio
from shapely.ops import transform as shapely_transform

from aereo.client import AereoClient
import sys

_helpers = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(_helpers))
from eoids import mosaic_eoids_tiles, scan_eoids_dir
from aereo.execution import LocalProcessBackend
from aereo.interfaces import AereoProfile, GridConfig

# --- Configuration ---
# Use a historical date known to have Sentinel-2 coverage over AOI.
DATE_START = datetime(2024, 4, 8, 14, 0, tzinfo=timezone.utc)
DATE_END = datetime(2024, 4, 9, 15, 0, tzinfo=timezone.utc)
URI = "/tmp/03_sentinel2_msi_extraction"

# Shared AOI — path relative to this script so it works regardless of CWD
try:
    data_dir = Path(__file__).parent / ".." / "data"
except NameError:
    data_dir = Path().resolve() / "examples" / "data"

geojson_path = data_dir / "chocon.geojson"
gdf = gpd.read_file(geojson_path)
aoi = gdf.geometry.iloc[0]

# %%
# Load profiles and grid config from YAML.
all_profiles = {p.name: p for p in AereoProfile.from_yaml(data_dir / "profiles.yaml")}
grid = GridConfig.from_yaml(data_dir / "grid_config.yaml")

# Select the profile to use for extraction.
profiles = [all_profiles["s2_rgb"]]

# --- Client Setup ---
client = AereoClient()
print("Searching...", flush=True)
results = client.search(
    profiles=profiles,
    start_datetime=DATE_START,
    end_datetime=DATE_END,
    intersects=aoi,
)
print(results[["collection", "start_time", "end_time"]].to_string())
# %%
# plt union_all and aoi as overlay
fig, ax = plt.subplots()
results.geometry.plot(ax=ax, color="blue", alpha=0.5)
xs, ys = aoi.exterior.xy
ax.plot(xs, ys, color="red", linewidth=2, label="AOI boundary")
# %%
# Keep a single representative asset to keep the example fast
# results = results.drop_duplicates(subset=["collection"])
print(f"Kept {len(results)} representative result(s)")

# %%
# Prepare extraction tasks using the same profiles.
# cells_per_chunk=1 keeps the example fast and lightweight.
tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    grid_config=grid,
    target_aoi=aoi,
    uri=URI,
    profiles=profiles,
    cells_per_chunk=3,
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)

# For the smoke test we keep only the first task to stay within memory limits.
# In production you would extract all tasks.
# tasks = tasks[:1]
print(f"Extracting {len(tasks)} task(s)...", flush=True)
start_time = time.time()
backend = LocalProcessBackend(max_workers=2)
results_df = client.execute_tasks(tasks, backend=backend)
print(f"Extraction completed in {time.time() - start_time:.2f} seconds")
print(f"Extracted {len(results_df)} artifacts")

# %%
# --- Mosaic & plot RGB composite ---
# Discover unique collections that were actually extracted
entries = scan_eoids_dir(URI)
collections = sorted({e["collection"] for e in entries})
print(f"Collections to mosaic: {collections}")

# --- Verify one profile = one multi-band file ---
# The s2_rgb profile above declares three bands. By design this produces a
# single 3-band GeoTIFF per grid cell (Band 1 = B04, Band 2 = B03, Band 3 = B02).
artifact_paths = [e["path"] for e in entries if e.get("profile") == "s2_rgb"]
if artifact_paths:
    with rasterio.open(artifact_paths[0]) as src:
        print(f"Verified artifact: {artifact_paths[0].name}")
        print(f"  Bands: {src.count} (expected 3 for B04+B03+B02)")
        print(f"  Shape: {src.shape}")

# One AereoProfile produces exactly one multi-band artifact.
# Load it once via ``profile=profiles[0].name`` (which derives collection
# and variable from the AereoProfile) and index the bands directly.
# We set ``sort_by_coverage=False`` because Sentinel-2 tiles are dense
# rectangles — the coverage sort would read every tile into memory just
# to count pixels, which is very slow when mosaicking many tiles.
# ``target_resolution=0.001`` (~100 m in degrees) keeps the preview fast
# while still looking sharp on an 8" plot at 150 dpi.
mosaic, transform, crs = mosaic_eoids_tiles(
    URI,
    profile=profiles[0].name,
    sort_by_coverage=True,
    target_resolution=0.01,
)

# Band order in the mosaic matches profile.collections order:
# Band 1 = B04 (Red), Band 2 = B03 (Green), Band 3 = B02 (Blue)
rgb = mosaic.transpose(1, 2, 0).astype(np.float32)  # (3, H, W) -> (H, W, 3)

# Mask invalid pixels (nodata = 0, NaN)
valid_mask = np.all((rgb > 0) & np.isfinite(rgb), axis=-1)
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
print(rgb.shape)
ax.imshow(rgb, extent=extent)

# Reproject AOI boundary to mosaic CRS and overlay it
transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
aoi_projected = shapely_transform(transformer.transform, aoi)
xs, ys = aoi_projected.exterior.xy
ax.plot(xs, ys, color="red", linewidth=2, label="AOI boundary")

ax.legend(loc="upper right")
ax.set_title(f"Sentinel-2 L2A RGB @ 10 m – {collections[0]}")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
plt.tight_layout()
plt.savefig("/tmp/03_sentinel2_rgb.png", dpi=150)
print("Saved RGB mosaic to /tmp/03_sentinel2_rgb.png")
# %%
import rioxarray  # noqa: E402

rioxarray.open_rasterio(
    "/tmp/03_sentinel2_msi_extraction/loc-89D118L/date-20240409/profile-s2_rgb/loc-89D118L_start-20240409T142711_end-20240409T142711_profile-s2_rgb_collection-sentinel-2-l2a_variable-B04+B03+B02_res-10m.tif"
)
