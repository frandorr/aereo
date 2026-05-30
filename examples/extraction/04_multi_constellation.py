# ruff: noqa: E402
# %%
# 04_multi_constellation.py
# Multi-sensor comparison: search VIIRS + GOES + Sentinel-3 over a broad window,
# filter to one asset per sensor, extract all into the same EOIDS directory,

# NASA sensors (VIIRS, Sentinel-3) require Earthdata auth.
# Ensure ~/.netrc exists or EARTHDATA_USERNAME/PASSWORD are set.

from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from aereo.backends import LocalProcessBackend
from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig

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

# Load shared profiles and grid config from YAML.
all_profiles = {p.name: p for p in AereoProfile.from_yaml(data_dir / "profiles.yaml")}
grid = GridConfig.from_yaml(data_dir / "grid_config.yaml")

profiles = [
    all_profiles["goes_c02"],  # GOES-19
    all_profiles["viirs_i1"],  # VIIRS
    all_profiles["olci_o08"],  # Sentinel-3
]

# --- Client Setup ---
client = AereoClient(
    profiles=profiles,
    grid_config=grid,
    aoi=aoi,
    backend=LocalProcessBackend(max_workers=4),
)

print("Searching...", flush=True)
results = client.search(
    start_datetime=DATE_START,
    end_datetime=DATE_END,
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
    uri=URI,
    cells_per_task=2,
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)
print("Extracting...", flush=True)

results_df = client.execute_tasks(tasks)
print(f"Extracted {len(results_df)} artifacts")

# %%
import matplotlib.pyplot as plt
import rioxarray  # noqa: F401
import xarray as xr

# plot in 3 cols (one per row uri) — each at its native pixel size
subset = results_df[results_df.grid_cell == "90D_119L"]
uris = subset.uri.tolist()
n = len(uris)
cols = 3
rows = (n + cols - 1) // cols

COLLECTION_TO_CONSTELLATION = {
    "ABI-L1b-RadF": "GOES",
    "VJ202IMG": "VIIRS",
    "VJ203IMG": "VIIRS",
    "S3A_OL_1_EFR": "Sentinel-3",
}

fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows))
if n == 1:
    axes = [axes]
else:
    axes = axes.flatten()

for ax, (_, row) in zip(axes, subset.iterrows()):
    da = xr.open_dataarray(row.uri, engine="rasterio")
    da.plot(ax=ax, add_colorbar=False)
    ax.set_title(COLLECTION_TO_CONSTELLATION.get(row.collection, row.collection))

# hide unused subplots
for ax in axes[n:]:
    ax.axis("off")

plt.tight_layout()
plt.savefig("/root/repos/aereo/docs/assets/04_multi_constellation.png", dpi=150)
print("Saved plot to docs/assets/04_multi_constellation.png")
