# %%
# 04_conform_to_ml.py
# ML-ready extraction with fixed tensor shapes.  Derive ``conform_to`` from a
# geographic patch size, add padding for CNN receptive fields, and visualise as
# a montage.
#
# Common AerProfile pitfalls (documented inline):
#   1. Forgetting ``conform_to`` is ``(width, height)`` not ``(height, width)`` —
#      it matches rasterio ``(bands, height, width)`` convention.
#   2. ``padding`` increases extracted size beyond ``conform_to`` — the valid
#      region is ``conform_to``, total is ``conform_to + 2*padding``.
#   3. ``target_grid_dist`` and ``conform_to * resolution`` must agree —
#      mismatch causes unexpected geographic extents.

from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from aer.client import AerClient
from aer.interfaces import AerProfile, GridConfig

# --- Configuration ---
# Use a historical date known to have Sentinel-2 coverage over Chocon AOI.
DATE_START = datetime(2024, 4, 9, 14, 0, tzinfo=timezone.utc)
DATE_END = datetime(2024, 4, 9, 15, 0, tzinfo=timezone.utc)
URI = "/tmp/04_conform_to_ml_extraction"

PATCH_KM = 2_560  # meters — at 10 m resolution this gives 256 px per side
RESOLUTION = 10  # Sentinel-2 10 m bands

# Derive fixed shape from geographic patch size.
conform_shape = (PATCH_KM // RESOLUTION, PATCH_KM // RESOLUTION)  # (256, 256)

# Shared AOI — path relative to this script so it works regardless of CWD
try:
    geojson_path = Path(__file__).parent / ".." / "data" / "chocon.geojson"
except NameError:
    geojson_path = Path().resolve() / "examples" / "data" / "chocon.geojson"

gdf = gpd.read_file(geojson_path)
aoi = gdf.geometry.iloc[0]

# %%
profiles = [
    AerProfile(
        name="s2_ml",
        resolution=10,
        collections={"sentinel-2-l2a": ["B04", "B03", "B02", "B08"]},
        plugin_hints={
            "search": "search_planetary_computer",
            "extract": "extract_odc_stac",
        },
        extract_params={"assets": ["B04", "B03", "B02", "B08"]},
        conform_to=conform_shape,
        padding=16,
    )
]

# --- Client Setup ---
client = AerClient()
print("Searching...", flush=True)
results = client.search(
    profiles=profiles,
    start_datetime=DATE_START,
    end_datetime=DATE_END,
    intersects=aoi,
)
print(results[["collection", "start_time", "end_time"]].to_string())

# Keep a single representative asset to keep the example fast
results = results.drop_duplicates(subset=["collection"])
print(f"Kept {len(results)} representative result(s)")

# %%
# Prepare extraction tasks with conform_to and padding.
# padding=16 means each side gets 16 extra pixels, so the total raster
# dimensions are conform_shape + 2*padding = (288, 288).
grid = GridConfig(
    target_grid_dist=PATCH_KM,
    target_grid_overlap=False,
)

tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    grid_config=grid,
    target_aoi=aoi,
    uri=URI,
    profiles=profiles,
    cells_per_chunk=1,
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)

# For the smoke test we keep only the first task to stay within memory limits.
# In production you would extract all tasks.
tasks = tasks[:1]
print(f"Extracting {len(tasks)} task(s)...", flush=True)

results_df = client.extract_batches(
    tasks,
    max_batch_workers=None,
)
print(f"Extracted {len(results_df)} artifacts")

# %%
# --- Stack into ML-ready tensor and verify uniform shapes ---
import numpy as np  # noqa: E402
import rasterio  # noqa: E402

# Load from the unique artifact URIs (fall back to glob if empty).
unique_uris = sorted({Path(u) for u in results_df["uri"].unique()})
tifs = unique_uris or sorted(Path(URI).rglob("*.tif"))
if not tifs:
    raise RuntimeError("No GeoTIFF outputs found — extraction may have failed.")

arrays = []
for tif in tifs:
    with rasterio.open(tif) as src:
        arr = src.read()  # (C, H, W)
        arrays.append(arr)
        print(f"  {tif.name}: {arr.shape}")

stack = np.stack(arrays)  # (N, C, H, W)
print(f"ML-ready tensor: {stack.shape}")

# With padding=16 the spatial size is conform_shape + 2*padding.
pad = profiles[0].padding or 0
expected_shape = (
    conform_shape[0] + 2 * pad,
    conform_shape[1] + 2 * pad,
)
actual_shape = stack.shape[-2:]
assert actual_shape == expected_shape, (
    f"Expected spatial shape {expected_shape} (conform_to + 2*padding), "
    f"got {actual_shape}"
)
print(f"All cells have uniform shape: {actual_shape} ✓")

# %%
# --- Montage visualization ---
import matplotlib.pyplot as plt  # noqa: E402

n = len(arrays)
cols = min(n, 4)
rows = (n + cols - 1) // cols
fig, axes = plt.subplots(rows, cols, figsize=(3 * cols, 3 * rows), squeeze=False)
fig.suptitle(
    f"conform_to={conform_shape}  |  padding={profiles[0].padding}  |  total={actual_shape}",
    fontsize=12,
    fontweight="bold",
)

for idx, arr in enumerate(arrays):
    ax = axes.flat[idx]
    band = arr[0]  # (C, H, W) -> (H, W)
    valid = band[(band != 0) & np.isfinite(band)]
    if len(valid) > 0:
        vmin, vmax = np.percentile(valid, [2, 98])
    else:
        vmin, vmax = 0, 1
    ax.imshow(band, vmin=vmin, vmax=vmax, cmap="viridis")
    ax.set_title(f"Cell {idx + 1}\n{band.shape}", fontsize=9)
    ax.axis("off")

for idx in range(n, rows * cols):
    axes.flat[idx].axis("off")

plt.tight_layout()
plt.savefig("/tmp/04_conform_to_montage.png", dpi=150)
print("Saved montage to /tmp/04_conform_to_montage.png")
