# %%
# 02_sentinel2_msi.py
# Sentinel-2 MSI via Planetary Computer: search → extract → true-color RGB composite.
#
# Common AerProfile pitfalls (documented inline):
#   1. Using old plugin name ``search_pc_sentinel2`` → PluginNotFoundError.
#      Use ``search_planetary_computer`` (generic PC search) instead.
#   2. Wrong collection name (``sentinel-2-l1c`` vs ``sentinel-2-l2a``) → empty results.
#   3. Bands are declared in ``profile.collections``, n
# ot ``extract_params["assets"]``.
#      ``extract_odc_stac`` reads bands from the collections mapping directly.

from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from aer.client import AerClient
from aer.interfaces import AerProfile

# --- Configuration ---
# Use a historical date known to have Sentinel-2 coverage over Chocon AOI.
# (Planetary Computer STAC does not have future-dated data.)
DATE_START = datetime(2024, 4, 9, 14, 0, tzinfo=timezone.utc)
DATE_END = datetime(2024, 4, 9, 15, 0, tzinfo=timezone.utc)
URI = "/tmp/02_sentinel2_msi_extraction"

# Shared AOI — path relative to this script so it works regardless of CWD
try:
    geojson_path = Path(__file__).parent / ".." / "data" / "chocon.geojson"
except NameError:
    geojson_path = Path().resolve() / "examples" / "data" / "chocon.geojson"

gdf = gpd.read_file(geojson_path)
aoi = gdf.geometry.iloc[0]

# %%
# Profiles are usually loaded from a YAML or JSON config file. Here we create the
# AerProfile directly to keep the example self-contained.
#
# Key differences from satpy-based examples:
#   - No ``reader`` or ``calibration`` in extract_params — odc-stac reads STAC
#     assets directly from Planetary Computer signed URLs.
#   - ``collections`` uses the Planetary Computer collection ID (``sentinel-2-l2a``).
#   - ``plugin_hints["search"]`` points to ``search_planetary_computer`` (generic
#     STAC search), NOT the old ``search_pc_sentinel2``.
profiles = [
    AerProfile(
        name="s2_rgb",
        resolution=10,
        # One AerProfile produces exactly one artifact file per grid cell.
        # All variables declared here (B04, B03, B02) become separate bands
        # inside that single GeoTIFF — not separate files.
        collections={"sentinel-2-l2a": ["B04", "B03", "B02"]},
        plugin_hints={
            "search": "search_planetary_computer",
            "extract": "extract_odc_stac",
        },
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
# %%
_ = results.head(10)
# %%
# Keep a single representative asset to keep the example fast
# results = results.drop_duplicates(subset=["collection"])
print(f"Kept {len(results)} representative result(s)")

# %%
# Prepare extraction tasks using the same profiles.
# We use a fine target_grid_dist (25.6 km) because Sentinel-2 MSI native
# resolution is 10 m, so ~2560 px per cell.
# cells_per_chunk=1 keeps the example fast and lightweight.
tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    target_aoi=aoi,
    uri=URI,
    profiles=profiles,
    target_grid_dist=25_600,
    target_grid_overlap=False,
    target_grid_margin=6.8,
    grid_filter_mode="within",
    prepare_params={"cells_per_chunk": 1},
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)

# For the smoke test we keep only the first task to stay within memory limits.
# In production you would extract all tasks.
# tasks = tasks[:1]
print(f"Extracting {len(tasks)} task(s)...", flush=True)

results_df = client.extract_batches(
    tasks,
    max_batch_workers=8,
)
print(f"Extracted {len(results_df)} artifacts")
# %%
_ = tasks
# %%
# --- Mosaic & plot RGB composite ---
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from aer.eoids import mosaic_eoids_tiles, scan_eoids_dir  # noqa: E402
from pyproj import Transformer  # noqa: E402
from shapely.ops import transform as shapely_transform  # noqa: E402

# Discover unique collections that were actually extracted
entries = scan_eoids_dir(URI)
collections = sorted({e["collection"] for e in entries})
print(f"Collections to mosaic: {collections}")

# --- Verify one profile = one multi-band file ---
# The s2_rgb profile above declares three bands. By design this produces a
# single 3-band GeoTIFF per grid cell (Band 1 = B04, Band 2 = B03, Band 3 = B02).
artifact_paths = [e["path"] for e in entries if e.get("profile") == "s2_rgb"]
if artifact_paths:
    import rasterio  # noqa: E402

    with rasterio.open(artifact_paths[0]) as src:
        print(f"Verified artifact: {artifact_paths[0].name}")
        print(f"  Bands: {src.count} (expected 3 for B04+B03+B02)")
        print(f"  Shape: {src.shape}")

# Mosaic each band separately and stack into RGB.
# We set ``sort_by_coverage=False`` because Sentinel-2 tiles are dense
# rectangles — the coverage sort would read every tile into memory just
# to count pixels, which is very slow when mosaicking many tiles.
# ``target_resolution=0.001`` (~100 m in degrees) keeps the preview fast
# while still looking sharp on an 8" plot at 150 dpi.
band_order = ["B04", "B03", "B02"]  # Red, Green, Blue
band_mosaics = []
for band in band_order:
    mosaic, transform, crs = mosaic_eoids_tiles(
        URI,
        collection=collections[0],
        variable=band,
        sort_by_coverage=False,
        target_resolution=0.001,
    )
    band_mosaics.append(mosaic[0])  # (1, H, W) -> (H, W)

# Stack to (H, W, 3) for RGB display
rgb = np.stack(band_mosaics, axis=-1).astype(np.float32)

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
plt.savefig("/tmp/02_sentinel2_rgb.png", dpi=150)
print("Saved RGB mosaic to /tmp/02_sentinel2_rgb.png")
