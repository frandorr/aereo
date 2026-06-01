# %%
# basic_extract.py
# Minimal AEREO extraction example using PipelineProfile.
#
# This example demonstrates a full search → prepare → extract workflow
# with processor configuration, including parallel NDVI and NDWI
# computation in the post-processing stage.

from datetime import datetime, timezone

from aereo.client import AereoClient
from aereo.interfaces import GridConfig, PipelineProfile
from shapely.geometry import box

profile = PipelineProfile(
    name="s2_ndvi_ndwi",
    resolution=100,
    collections={"sentinel-2-l2a": ["B04", "B08", "B11"]},
    plugin_hints={"search": "planetary_computer", "read": "odc_stac"},
    search_params={"cloud_cover": 20},
    pre_processors=[{"select_bands": {"bands": ["B04", "B08", "B11"]}}],
    post_processors=[
        {"parallel": ["compute_ndvi", "compute_ndwi"]},
        "normalize",
    ],
)

client = AereoClient(
    profiles=[profile],
    grid_config=GridConfig(target_grid_dist=10_000),
    aoi=box(-70.5, -33.5, -70.0, -33.0),
)

results = client.search(
    start_datetime=datetime(2024, 4, 8, tzinfo=timezone.utc),
    end_datetime=datetime(2024, 4, 9, tzinfo=timezone.utc),
)

tasks = client.prepare_for_extraction(
    results,
    uri="/tmp/basic_extract_out",
    cells_per_task=1,
)

results_df = client.execute_tasks(tasks)
print(f"Extracted {len(results_df)} artifacts")
print(results_df.head())
