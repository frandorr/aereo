# ruff: noqa: E402
# %%
# 03_sentinel2_msi.py
# Sentinel-2 MSI via Planetary Computer: search → extract → true-color RGB composite.

import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from aereo.backends import LocalProcessBackend
from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig

# --- Configuration ---
# Use a historical date known to have Sentinel-2 coverage over AOI.
DATE_START = datetime(2024, 4, 8, 14, 0, tzinfo=timezone.utc)
DATE_END = datetime(2024, 4, 9, 15, 0, tzinfo=timezone.utc)
URI = "/tmp/03_sentinel2_msi_extraction"

# Shared AOI — path relative to this script so it works regardless of CWD
try:
    data_dir = Path(__file__).parent / ".." / "data"
except NameError:
    data_dir = Path().resolve() / "examples" / "data"

geojson_path = data_dir / "chocon.geojson"
gdf = gpd.read_file(geojson_path)
aoi = gdf.geometry.iloc[0]
# Load profiles and grid config from YAML.
all_profiles = {p.name: p for p in AereoProfile.from_yaml(data_dir / "profiles.yaml")}
grid = GridConfig.from_yaml(data_dir / "grid_config.yaml")

# Select the profile to use for extraction.
profiles = [all_profiles["s2_rgb"]]

# --- Client Setup ---
# cells_per_task=3 keeps the example fast and lightweight.
client = AereoClient(
    profiles=profiles,
    grid_config=grid,
    aoi=aoi,
    backend=LocalProcessBackend(max_workers=8),
)

print("Searching...", flush=True)
results = client.search(
    start_datetime=DATE_START,
    end_datetime=DATE_END,
)
print(results[["collection", "start_time", "end_time"]].to_string())
# %%
# Prepare extraction tasks using the same profiles.
# cells_per_task=3 keeps the example fast and lightweight.
tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    uri=URI,
    cells_per_task=3,
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)

# For the smoke test we keep only the first task to stay within memory limits.
# In production you would extract all tasks.
# tasks = tasks[:1]
print(f"Extracting {len(tasks)} task(s)...", flush=True)
start_time = time.time()
results_df = client.execute_tasks(tasks)
print(f"Extraction completed in {time.time() - start_time:.2f} seconds")
print(f"Extracted {len(results_df)} artifacts")
# %%
import rioxarray

rioxarray.open_rasterio(results_df.iloc[0].uri)[0].plot()
