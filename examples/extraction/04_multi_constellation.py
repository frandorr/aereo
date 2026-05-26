# %%
# 04_multi_constellation.py
# Multi-sensor comparison: search VIIRS + GOES + Sentinel-3 over a broad window,
# filter to one asset per sensor, extract all into the same EOIDS directory,
# then mosaic side-by-side.
#
# Common AereoProfile pitfalls (documented inline):
#   1. Missing geolocation collection VJ203IMG for VIIRS → satpy raises KeyError
#      for missing geolocation arrays. Always pair VJ202IMG with VJ203IMG.
#   2. Forgetting downloader for earthaccess-based sensors → assets cannot be
#      downloaded. Use aer.search_earthaccess.earthaccess_download_wrapper.
#   3. Missing extract_params["reader"] → satpy raises ReaderNotAvailable.
#
# NASA sensors (VIIRS, Sentinel-3) require Earthdata auth.
# Ensure ~/.netrc exists or EARTHDATA_USERNAME/PASSWORD are set.

from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from aereo.client import AereoClient
from aereo.eoids import mosaic_eoids_tiles, scan_eoids_dir
from aereo.execution import LocalProcessBackend
from aereo.interfaces import AereoProfile, GridConfig
from pyproj import Transformer
from shapely.ops import transform as shapely_transform

# --- Configuration ---
DATE_START = datetime(2026, 4, 2, 0, 0, tzinfo=timezone.utc)
DATE_END = datetime(2026, 4, 3, 0, 0, tzinfo=timezone.utc)
URI = "/tmp/04_multi_constellation_extraction"

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

profiles = [
    all_profiles["goes_c02"],
    all_profiles["viirs_i1"],
    all_profiles["olci_o08"],
]

# --- Client Setup ---
client = AereoClient()
print("Searching...", flush=True)
results = client.search(
    profiles=profiles,
    start_datetime=DATE_START,
    end_datetime=DATE_END,
    intersects=aoi,
)

# Keep one representative asset per collection and ensure full AOI coverage.
# We further filter to known daytime granules that contain the bands we need.
results = results[
    (
        (results["collection"] == "VJ202IMG")
        & (results["start_time"] == "2026-04-02 17:54:00")
    )
    | (
        (results["collection"] == "VJ203IMG")
        & (results["start_time"] == "2026-04-02 17:54:00")
    )
    | (
        (results["collection"] == "S3A_OL_1_EFR")
        & (results["start_time"] == "2026-04-02 14:06:49")
    )
    | (
        (results["collection"] == "ABI-L1b-RadF")
        & (results["start_time"] == "2026-04-02 15:00:20")
    )
]
results = results[results.geometry.contains(aoi)]
print(f"Kept {len(results)} representative result(s) containing AOI")

# %%
# Prepare extraction tasks.

tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    grid_config=grid,
    target_aoi=aoi,
    uri=URI,
    profiles=profiles,
    cells_per_chunk=2,
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)
print("Extracting...", flush=True)

backend = LocalProcessBackend(max_workers=8)
results_df = client.execute_tasks(tasks, backend=backend)
print(f"Extracted {len(results_df)} artifacts")

# %%
# --- Mosaic & plot side-by-side ---


def _mask_invalid(data, is_viirs=False):
    """Mask NaN, zero-fill, and VIIRS uint16 sentinel as NaN (float32)."""
    data = data.astype(np.float32)
    invalid = np.isnan(data) | (data == 0)
    if is_viirs:
        invalid |= data == 65535
    return np.where(invalid, np.nan, data)


def _robust_vmin_vmax(data, lower=1, upper=99):
    """Compute percentile stretch excluding NaN."""
    valid = data[~np.isnan(data)]
    if len(valid) == 0:
        return 0, 1
    vmin, vmax = np.percentile(valid, [lower, upper])
    if vmin == vmax:
        vmin, vmax = valid.min(), valid.max()
    return float(vmin), float(vmax)


# Discover unique collections that were actually extracted
entries = scan_eoids_dir(URI)
collections = sorted({e["collection"] for e in entries})
print(f"Collections to mosaic: {collections}")

# Map each collection to a sensor-friendly title
_titles = {
    "ABI-L1b-RadF": "GOES-19 ABI C02",
    "VJ202IMG": "VIIRS I01",
    "VJ203IMG": "VIIRS Geolocation",
    "S3A_OL_1_EFR": "Sentinel-3 OLCI Oa08",
}

n = len(collections)
cols = min(n, 3)
rows = (n + cols - 1) // cols
fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.5 * rows), squeeze=False)
fig.suptitle("Multi-Constellation Extraction", fontsize=12, fontweight="bold")

for ax, col in zip(axes.flat, collections):
    print(f"Mosaicking {col} ...", flush=True)
    try:
        mosaic, transform, crs = mosaic_eoids_tiles(URI, collection=col)
        band = mosaic[0] if mosaic.ndim == 3 else mosaic
        band = _mask_invalid(band, is_viirs=("VJ202IMG" in col or "VJ203IMG" in col))
        valid = band[~np.isnan(band)]
        if len(valid) == 0:
            ax.set_title(f"{_titles.get(col, col)}\n(no data)")
            ax.axis("off")
            continue
        vmin, vmax = _robust_vmin_vmax(band)
        h, w = band.shape
        extent = (
            transform.c,
            transform.c + transform.a * w,
            transform.f + transform.e * h,
            transform.f,
        )
        ax.imshow(
            band,
            cmap="viridis",
            vmin=vmin,
            vmax=vmax,
            interpolation="nearest",
            extent=extent,
        )

        # Reproject AOI boundary to mosaic CRS and overlay it
        transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        aoi_projected = shapely_transform(transformer.transform, aoi)
        xs, ys = aoi_projected.exterior.xy
        ax.plot(xs, ys, color="red", linewidth=2, label="AOI boundary")

        ax.set_title(_titles.get(col, col), fontsize=10)
        ax.axis("off")
    except Exception as exc:
        ax.set_title(f"{_titles.get(col, col)}\n{exc}")
        ax.axis("off")

for ax in axes.flat[n:]:
    ax.axis("off")

plt.tight_layout()
plt.savefig("/tmp/04_multi_constellation.png", dpi=150)
print("Saved mosaic to /tmp/04_multi_constellation.png")
# %%
