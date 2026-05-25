# %%
# 01_minimal_goes.py
# Minimal AER workflow: search GOES-19 ABI C02, extract to GeoTIFF.

from datetime import datetime, timezone

from aer.client import AerClient
from aer.interfaces import AerProfile, GridConfig
from shapely.geometry import box

profile = AerProfile(
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

client = AerClient(
    profiles=[profile],
    grid_config=GridConfig(target_grid_dist=256_000),
    aoi=box(-70, -40, -68, -39),
)

results = client.search(
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 10, tzinfo=timezone.utc),
)

tasks = client.prepare_for_extraction(
    results,
    uri="/tmp/01_minimal_goes_out",
)

client.execute_tasks(tasks)
print("GeoTIFFs written to /tmp/01_minimal_goes_out")
