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
except NameError:
    # Jupyter cells: fall back to repo root
    geojson_path = Path().resolve() / "examples" / "data" / "chocon.geojson"
gdf = gpd.read_file(geojson_path)
aoi = gdf.geometry.iloc[0]


# %%
# Profiles are loaded from a YAML config file.  Each profile declares its
# collections, variables, channels, satellite, and which plugins to use (via
# plugin_hints).  The *downloader* field accepts a dotted import path string
# (e.g. ``aer.search_earthaccess.earthaccess_download_wrapper``) which
# Pydantic resolves to a live callable at load time.
profiles = AerProfile.from_yaml(Path(__file__).parent / ".." / "profiles.yaml")
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
    | (
        (results["collection"] == "MOD021KM")
        & (results["start_time"] == "2026-04-02 13:50:00")
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
# --- Keep only assets that fully contain the AOI ---
results = results[results.geometry.contains(aoi)]
# GOES returns many channel files for the same slot; keep one per collection
results = results.drop_duplicates(subset=["collection"])
print(f"Kept {len(results)} hardcoded results for testing:")
print(results[["collection", "start_time", "end_time"]].to_string())

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
    results,
    target_aoi=aoi,
    uri=URI,
    profiles=profiles,
    target_grid_dist=256000,
    target_grid_overlap=False,
    prepare_params={"cells_per_chunk": 2},
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
