# %%
# 01_minimal_goes.py
# Minimal AER workflow: search GOES-19 ABI C02, extract to GeoTIFF.

from datetime import datetime, timezone

from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig
from shapely.geometry import box

client = AereoClient()
aoi = box(-70, -40, -68, -39)
profile = AereoProfile(
    name="goes",
    resolution=1000,
    collections={"ABI-L1b-RadF": ["C02"]},
    plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
    search_params={"satellite": "GOES-19"},
    extract_params={
        "reader": "abi_l1b",
        "calibration": "reflectance",
        "delay_writes": True,
    },
)
results = client.search(
    profiles=[profile],
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 10, tzinfo=timezone.utc),
    intersects=aoi,
)
tasks = client.prepare_for_extraction(
    results,
    profiles=[profile],
    uri="/tmp/01_minimal_goes_out",
    grid_config=GridConfig(target_grid_dist=256000),
    target_aoi=aoi,
)
client.execute_tasks(tasks)
print("GeoTIFFs written to /tmp/01_minimal_goes_out")
