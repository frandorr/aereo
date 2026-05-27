# ruff: noqa: E402
# %%

from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from aereo.backends import (
    LocalProcessBackend,  # we are going to use an explicit backend this time
)
from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig

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

# Load shared profiles and grid config from YAML.
all_profiles = {p.name: p for p in AereoProfile.from_yaml(data_dir / "profiles.yaml")}
grid = GridConfig.from_yaml(data_dir / "grid_config.yaml")

profiles = [all_profiles["goes_c02"]]

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
print(results[["collection", "start_time", "end_time"]].to_string())


tasks = client.prepare_for_extraction(
    results,  # type: ignore[arg-type]
    uri=URI,
    cells_per_task=4,
)


results_df = client.execute_tasks(tasks)
print(f"Extracted {len(results_df)} artifacts")
# %%
# import rioxarray

# rioxarray.open_rasterio(results_df.iloc[0].uri).plot()
