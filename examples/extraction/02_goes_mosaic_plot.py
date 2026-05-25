# %%
# 02_goes_mosaic_plot.py
# GOES-19 ABI workflow: search, extract, mosaic and plot.
#
# Common AerProfile pitfalls (documented inline):
#   1. Forgetting search_params={"satellite": "GOES-19"} → search returns empty or wrong satellite.
#   2. Forgetting extract_params["reader"] → satpy raises ReaderNotAvailable.

from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer
from shapely.ops import transform as shapely_transform

from aereo.client import AerClient
from aereo.eoids import mosaic_eoids_tiles, scan_eoids_dir
from aereo.execution import LocalProcessBackend
from aereo.interfaces import AerProfile, GridConfig

# --- Configuration ---
DATE_START = datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc)
DATE_END = datetime(2026, 4, 2, 14, 9, tzinfo=timezone.utc)
URI = "/tmp/02_goes_mosaic_plot_extraction"

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
all_profiles = {p.name: p for p in AerProfile.from_yaml(data_dir / "profiles.yaml")}
grid = GridConfig.from_yaml(data_dir / "grid_config.yaml")

profiles = [all_profiles["goes_c02"]]

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
# Prepare extraction tasks using the same profiles.
# cells_per_chunk=1 keeps the example fast and lightweight.

tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    grid_config=grid,
    target_aoi=aoi,
    uri=URI,
    profiles=profiles,
    cells_per_chunk=1,
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)
print("Extracting...", flush=True)

backend = LocalProcessBackend(max_workers=4)
results_df = client.execute_tasks(tasks, backend=backend)
print(f"Extracted {len(results_df)} artifacts")

# %%
# --- Mosaic & plot extracted artifacts ---
# Discover unique collections that were actually extracted
entries = scan_eoids_dir(URI)
collections = sorted({e["collection"] for e in entries})
print(f"Collections to mosaic: {collections}")

mosaic, transform, crs = mosaic_eoids_tiles(URI, collection=collections[0])

fig, ax = plt.subplots(figsize=(8, 6))
band = mosaic[0]
valid = band[(band != 0) & np.isfinite(band)]
vmin, vmax = valid.min(), valid.max()

im = ax.imshow(
    band,
    extent=(
        transform.c,
        transform.c + transform.a * mosaic.shape[2],
        transform.f + transform.e * mosaic.shape[1],
        transform.f,
    ),
    vmin=vmin,
    vmax=vmax,
    cmap="Greys_r",
)

# Reproject AOI boundary to mosaic CRS and overlay it
transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
aoi_projected = shapely_transform(transformer.transform, aoi)
xs, ys = aoi_projected.exterior.xy
ax.plot(xs, ys, color="red", linewidth=2, label="AOI boundary")

ax.legend(loc="upper right")
fig.colorbar(im, ax=ax, shrink=0.6, label="Reflectance")
ax.set_title(f"GOES-19 C02 @ 1000 m – {collections[0]}")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
plt.tight_layout()
plt.savefig("/tmp/02_goes_mosaic_plot.png", dpi=150)
print("Saved mosaic to /tmp/02_goes_mosaic_plot.png")
