#!/usr/bin/env python
# coding: utf-8

# # VIIRS HTTP Download & Extraction
#
# This notebook demonstrates how to search for VIIRS granules via **earthaccess**, verify HTTPS/S3 URL columns, and extract imagery using **satpy**.

# ## Setup

# In[ ]:


from datetime import datetime, timezone
from pathlib import Path
import shutil
import time

import earthaccess
import geopandas as gpd

from aer.client import AerClient
from aer.interfaces import ExtractionProfile
from aer.search_earthaccess import earthaccess_download_wrapper


# ## Configuration

# In[ ]:


# --- Configuration ---
DATE_START = datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc)
DATE_END = datetime(2026, 4, 4, 15, 2, tzinfo=timezone.utc)

# Load AOI (Buenos Aires province)
geojson_path = Path("buenos_aires.geojson")
gdf = gpd.read_file(geojson_path)
aoi = gdf.geometry.iloc[0]

# Authenticate with Earthdata
earthaccess.login()

# --- Client Setup ---
client = AerClient()


# ## Search

# In[ ]:


print("Searching...", flush=True)
results = client.search(
    collections=["VJ202IMG", "VJ203IMG"],
    start_datetime=DATE_START,
    end_datetime=DATE_END,
    intersects=aoi,
    plugin_hints={
        "VJ202IMG": "search_earthaccess",
        "VJ203IMG": "search_earthaccess",
    },
)
print(f"Found {len(results)} results", flush=True)
results.head()


# ## Verify URL columns

# In[ ]:


assert "s3_url" in results.columns, "Missing s3_url column"
assert "https_url" in results.columns, "Missing https_url column"
print(f"Columns: {list(results.columns)}", flush=True)
print(f"Sample s3_url: {results['s3_url'].iloc[0]}", flush=True)
print(f"Sample https_url: {results['https_url'].iloc[0]}", flush=True)


# ## Prepare Extraction

# In[ ]:


# --- Prepare Extraction ---
uri = "extract_buenos_aires_viirs"

profiles = [
    ExtractionProfile(
        name="viirs_i4",
        resolution=400,
        collection_variables_map={"VJ202IMG": ["I04"], "VJ203IMG": []},
    )
]

tasks = client.prepare_for_extraction(
    results,
    target_aoi=aoi,
    uri=uri,
    profiles=profiles,
    target_grid_dist=256000,
    target_grid_overlap=False,
    prepare_params={"cells_per_chunk": 10},
    plugin_hints={"VJ202IMG": "extract_satpy", "VJ203IMG": "extract_satpy"},
)

print(f"Prepared {len(tasks)} extraction tasks", flush=True)


# ## Extract

# In[ ]:


# Clean output directory
uri_path = Path(uri)
if uri_path.exists():
    shutil.rmtree(uri_path)
uri_path.mkdir(parents=True)

print("Extracting...", flush=True)
start_time = time.time()

extract_params = {
    "padding": 2,
    "resampling": "nearest",
    "calibration": "radiance",
    "satellite": "NOAA21",
    "reader": "viirs_l1b",
    "downloader": earthaccess_download_wrapper,
}

results_df = client.extract_batches(
    tasks,
    extract_params=extract_params,
    plugin_hints={"VJ202IMG": "extract_satpy", "VJ203IMG": "extract_satpy"},
    max_batch_workers=2,
)

end_time = time.time()
print(f"Extraction took {end_time - start_time:.2f}s")
print(f"Extracted {len(results_df)} artifacts")


# ## Results

# In[ ]:


results_df[["id", "collection", "grid_cell", "uri"]].head()
