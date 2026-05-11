# %%
# --- Plot AOI on a map ---
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from aer.client import AerClient
from aer.interfaces import AerProfile
from aer.viz import plot_aoi

# --- Configuration ---
DATE_START = datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc)
DATE_END = datetime(2026, 4, 2, 20, 0, tzinfo=timezone.utc)
URI = "extraction_output_dir"

# Load AOI — path relative to this script so it works regardless of CWD
try:
    geojson_path = Path(__file__).parent / ".." / "data" / "chocon.geojson"
    profiles_path = Path(__file__).parent / ".." / "data" / "profiles.yaml"
except NameError:
    # Jupyter cells: fall back to repo root
    geojson_path = Path().resolve() / "examples" / "data" / "chocon.geojson"
    profiles_path = Path().resolve() / "examples" / "data" / "profiles.yaml"
gdf = gpd.read_file(geojson_path)
aoi = gdf.geometry.iloc[0]

# %%
# Profiles are loaded from a YAML config file.  Each profile declares its
# collections, variables, channels, satellite, and which plugins to use (via
# plugin_hints).  The *downloader* field accepts a dotted import path string
# (e.g. ``aer.search_earthaccess.earthaccess_download_wrapper``) which
# Pydantic resolves to a live callable at load time.
profiles = AerProfile.from_yaml(profiles_path)
# Verify the downloader was resolved from a string to a callable
assert profiles[0].downloader is not None

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
results.collection.unique()

# %%
# --- Keep only a few hardcoded results for testing ---
# (VJ202IMG and VJ203IMG share the same datetime; all are daylight over Argentina)
results = results[
    (
        (results["collection"] == "VJ202IMG")
        & (results["start_time"] == "2026-04-02 17:54:00")
    )
    | (
        (results["collection"] == "VJ203IMG")
        & (results["start_time"] == "2026-04-02 17:54:00")
    )
    # | (
    #     (results["collection"] == "MOD021KM")
    #     & (results["start_time"] == "2026-04-02 13:50:00")
    # )
    | (
        (results["collection"] == "S3A_OL_1_EFR")
        & (results["start_time"] == "2026-04-02 14:06:49")
    )
    | (
        (results["collection"] == "ABI-L1b-RadF")
        & (results["start_time"] == "2026-04-02 15:00:20")
    )
]
# --- Keep only assets that fully contain the AOI ---
results = results[results.geometry.contains(aoi)]
# GOES returns many channel files for the same slot; keep one per collection
results = results.drop_duplicates(subset=["collection"])  # type: ignore[call-overload]
print(f"Kept {len(results)} hardcoded results for testing:")
print(results[["collection", "start_time", "end_time"]].to_string())

# %%
print(results)
# --- Plot AOI with asset footprints ---
# %%
plot_aoi(
    gdf,
    label="Chocon AOI",
    buffer=0.5,
    width=4,
    height=5,
)
results.geometry
# %%
# Now we prepare the extraction tasks using the same profiles
tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    target_aoi=aoi,
    uri=URI,
    profiles=profiles,
    target_grid_dist=256000,
    target_grid_overlap=False,
    prepare_params={"cells_per_chunk": 10},
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)

# Clean output directory
uri_path = Path(URI)
if uri_path.exists():
    shutil.rmtree(uri_path)
uri_path.mkdir(parents=True)

print("Extracting...", flush=True)
start_time = time.time()

results_df = client.extract_batches(
    tasks,
    max_batch_workers=None,
)

end_time = time.time()
print(f"Extraction took {end_time - start_time:.2f}s")
print(f"Extracted {len(results_df)} artifacts")
# %%
print(results_df)

# %%
# --- Mosaic & plot extracted artifacts ---
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


def _plot_aoi_boundary(ax, aoi_geom, transform, color="yellow", linewidth=1.5):
    """Overlay the AOI boundary in pixel coordinates."""
    import rasterio.transform

    polys = list(aoi_geom.geoms) if aoi_geom.geom_type == "MultiPolygon" else [aoi_geom]
    for poly in polys:
        xs, ys = poly.exterior.coords.xy
        rows, cols = rasterio.transform.rowcol(transform, xs, ys)
        ax.plot(cols, rows, color=color, linewidth=linewidth)


def _plot_mosaic(
    ax, mosaic, transform, title, is_viirs=False, cmap="viridis", aoi_geom=None
):
    """Plot a single-band mosaic with percentile stretch and optional AOI boundary."""
    band = mosaic[0] if mosaic.ndim == 3 else mosaic
    band = _mask_invalid(band, is_viirs=is_viirs)
    valid = band[~np.isnan(band)]
    if len(valid) == 0:
        ax.set_title(f"{title}\n(no data)")
        ax.axis("off")
        return
    vmin, vmax = _robust_vmin_vmax(band)
    ax.imshow(band, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    if aoi_geom is not None:
        _plot_aoi_boundary(ax, aoi_geom, transform)
    ax.set_title(title, fontsize=10)
    ax.axis("off")


# Discover unique products that were actually extracted
entries = scan_eoids_dir(URI)
products = sorted({e["prod"] for e in entries})
print(f"Products to mosaic: {products}")

n = len(products)
cols = min(n, 3)
rows = (n + cols - 1) // cols
fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.5 * rows), squeeze=False)
fig.suptitle("Extracted artifacts", fontsize=12, fontweight="bold")

for ax, prod in zip(axes.flat, products):
    print(f"Mosaicking {prod} ...", flush=True)
    try:
        mosaic, transform, crs = mosaic_eoids_tiles(URI, product=prod)
        is_viirs = "VJ202IMG" in prod or "VJ203IMG" in prod
        _plot_mosaic(ax, mosaic, transform, prod, is_viirs=is_viirs, aoi_geom=aoi)
    except Exception as exc:
        ax.set_title(f"{prod}\n{exc}")
        ax.axis("off")

for ax in axes.flat[n:]:
    ax.axis("off")

plt.tight_layout()
plt.savefig("/tmp/extraction_mosaic.png", dpi=150)
