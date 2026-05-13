# %%
# 03_multi_constellation.py
# Multi-sensor comparison: search VIIRS + GOES + Sentinel-3 over a broad window,
# filter to one asset per sensor, extract all into the same EOIDS directory,
# then mosaic side-by-side.
#
# Common AerProfile pitfalls (documented inline):
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
from aer.client import AerClient
from aer.interfaces import AerProfile, GridConfig
from aer.search_earthaccess import earthaccess_download_wrapper

# --- Configuration ---
DATE_START = datetime(2026, 4, 2, 0, 0, tzinfo=timezone.utc)
DATE_END = datetime(2026, 4, 3, 0, 0, tzinfo=timezone.utc)
URI = "/tmp/03_multi_constellation_extraction"

# Shared AOI — path relative to this script so it works regardless of CWD
try:
    geojson_path = Path(__file__).parent / ".." / "data" / "chocon.geojson"
except NameError:
    geojson_path = Path().resolve() / "examples" / "data" / "chocon.geojson"

gdf = gpd.read_file(geojson_path)
aoi = gdf.geometry.iloc[0]

# %%
# Profiles for three different sensors, each using the appropriate search and
# extract plugins.  VIIRS and Sentinel-3 use earthaccess (NASA) which requires
# the downloader callable.
profiles = [
    AerProfile(
        name="goes_c02",
        resolution=1000,
        collections={"ABI-L1b-RadF": ["C02"]},
        plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
        extract_params={"reader": "abi_l1b", "calibration": "reflectance"},
        search_params={"satellite": "GOES-19"},
    ),
    AerProfile(
        name="viirs_i1",
        resolution=375,
        collections={"VJ202IMG": ["I01"], "VJ203IMG": []},
        plugin_hints={"search": "search_earthaccess", "extract": "extract_satpy"},
        extract_params={
            "reader": "viirs_l1b",
            "calibration": "reflectance",
            "resampling": "nearest",
        },
        downloader=earthaccess_download_wrapper,
    ),
    AerProfile(
        name="olci_o08",
        resolution=300,
        collections={"S3A_OL_1_EFR": ["Oa08"]},
        plugin_hints={"search": "search_earthaccess", "extract": "extract_satpy"},
        extract_params={
            "reader": "olci_l1b",
            "calibration": "reflectance",
            "resampling": "nearest",
        },
        downloader=earthaccess_download_wrapper,
    ),
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
print(results[["collection", "start_time", "end_time"]].to_string())  # type: ignore[union-attr]

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
print(results[["collection", "start_time", "end_time"]].to_string())  # type: ignore[union-attr]

# %%
# Prepare extraction tasks.  A compromise target_grid_dist (256 km) lets all
# sensors extract the same geographic region despite very different native
# resolutions.
grid = GridConfig(
    target_grid_dist=256_000,
    target_grid_overlap=False,
)

tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    grid_config=grid,
    target_aoi=aoi,
    uri=URI,
    profiles=profiles,
    cells_per_chunk=10,
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)
print("Extracting...", flush=True)

results_df = client.extract_batches(
    tasks,
    max_batch_workers=None,
)
print(f"Extracted {len(results_df)} artifacts")

# %%
# --- Mosaic & plot side-by-side ---
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from aer.eoids import mosaic_eoids_tiles, scan_eoids_dir  # noqa: E402


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
        ax.imshow(band, cmap="viridis", vmin=vmin, vmax=vmax, interpolation="nearest")
        ax.set_title(_titles.get(col, col), fontsize=10)
        ax.axis("off")
    except Exception as exc:
        ax.set_title(f"{_titles.get(col, col)}\n{exc}")
        ax.axis("off")

for ax in axes.flat[n:]:
    ax.axis("off")

plt.tight_layout()
plt.savefig("/tmp/03_multi_constellation.png", dpi=150)
print("Saved mosaic to /tmp/03_multi_constellation.png")
