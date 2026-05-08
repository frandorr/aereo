# %%
# --- Plot AOI on a map ---
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from aer.client import AerClient
from aer.interfaces import AerProfile
from aer.search_earthaccess import earthaccess_download_wrapper
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
# Profiles unify search + extraction config in a single ground-truth object.
# Each profile declares its collections, variables, channels, satellite, and
# which plugins to use (via plugin_hints).
profiles = [
    AerProfile(
        name="viirs_i1",
        resolution=375,
        collections=["VJ202IMG", "VJ203IMG"],
        collection_variables_map={"VJ202IMG": ["I01"], "VJ203IMG": []},
        channels=["I01"],
        reader="viirs_l1b",
        padding=2,
        resampling="nearest",
        calibration="reflectance",
        satellite="NOAA21",
        plugin_hints={"search": "search_earthaccess", "extract": "extract_satpy"},
    ),
    AerProfile(
        name="goes_c01",
        resolution=1000,
        collections=["ABI-L1b-RadF"],
        collection_variables_map={"ABI-L1b-RadF": ["C01"]},
        channels=["C01"],
        reader="abi_l1b",
        padding=2,
        resampling="nearest",
        calibration="reflectance",
        satellite="GOES-19",
        plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
    ),
    AerProfile(
        name="modis_thermal",
        resolution=1000,
        collections=["MOD021KM"],
        collection_variables_map={"MOD021KM": ["1"]},
        reader="modis_l1b",
        padding=2,
        resampling="nearest",
        calibration="reflectance",
        plugin_hints={"search": "search_earthaccess", "extract": "extract_satpy"},
    ),
    AerProfile(
        name="olci_rgb",
        resolution=300,
        collections=["S3A_OL_1_EFR"],
        collection_variables_map={"S3A_OL_1_EFR": ["Oa08"]},
        reader="olci_l1b",
        padding=2,
        resampling="nearest",
        calibration="reflectance",
        plugin_hints={"search": "search_earthaccess", "extract": "extract_satpy"},
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

# extract_params is reserved for meta-level / tool-level parameters.
# Domain-specific config (padding, calibration, reader, etc.) lives on the profile.
extract_params = {
    "downloader": earthaccess_download_wrapper,
}

results_df = client.extract_batches(
    tasks,
    extract_params=extract_params,
    max_batch_workers=None,
)

end_time = time.time()
print(f"Extraction took {end_time - start_time:.2f}s")
print(f"Extracted {len(results_df)} artifacts")
