# %%
# 01_minimal_goes.py
# Minimal AEREO workflow: search GOES-19 ABI C02, extract to GeoTIFF.

from datetime import datetime, timezone

from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig
from shapely.geometry import box

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

client = AereoClient(
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

results_df = client.execute_tasks(tasks)
print("GeoTIFFs written to /tmp/01_minimal_goes_out")
# %%
import matplotlib.pyplot as plt  # noqa: E402
import rioxarray  # noqa: E402, F401
import xarray as xr  # noqa: E402

da = xr.open_dataarray(results_df.iloc[0].uri, engine="rasterio")
da.plot()
plt.title("GOES")
plt.tight_layout()
plt.savefig("/root/repos/aereo/docs/assets/01_minimal_goes.png", dpi=150)
print("Saved plot to docs/assets/01_minimal_goes.png")
