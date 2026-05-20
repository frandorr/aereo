# %%
# --- Plot AOI on a map ---
from datetime import datetime, timezone

from aer.client import AerClient
from aer.interfaces import AerProfile, GridConfig
from shapely.geometry import box

# --- Configuration ---
DATE_START = datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc)
DATE_END = datetime(2026, 4, 2, 14, 9, tzinfo=timezone.utc)
URI = "/tmp/goes_extraction"

aoi = box(
    -69.75950213664814, -39.97992452755355, -68.24173711941097, -39.05094702427256
)

# %%
# Profiles are usually loaded from a YAML or JSON config file (AerProfile.from_yaml or AerProfile.from_json).
# Each profile declares its collections, variables, and which plugins to use (via
# plugin_hints). This time we just create the AerProfile directly from a dict.
profiles = [
    AerProfile(
        name="goes_c01",
        resolution=500,
        collections={"ABI-L1b-RadF": ["C02"]},
        plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
        extract_params={"reader": "abi_l1b", "calibration": "reflectance"},
        search_params={"satellite": "GOES-19"},
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
# %%
print(results[["collection", "start_time", "end_time"]].to_string())
# %%
# Now we prepare the extraction tasks using the same profiles
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
# --- Mosaic & plot extracted artifacts ---
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from aer.eoids import mosaic_eoids_tiles, scan_eoids_dir  # noqa: E402
from pyproj import Transformer  # noqa: E402
from shapely.ops import transform as shapely_transform  # noqa: E402

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
ax.set_title(f"GOES-19 C01 @ 1000 m – {collections[0]}")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
plt.tight_layout()
plt.savefig(f"{URI}/extraction_mosaic.png", dpi=150)
