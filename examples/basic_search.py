# %%
# basic_search.py
# Minimal AEREO search example using PipelineProfile.
#
# This example demonstrates how to search for satellite assets using the
# Hamilton-based PipelineProfile.  No extraction is performed.

from datetime import datetime, timezone

from aereo.client import AereoClient
from aereo.interfaces import PipelineProfile
from shapely.geometry import box

# Define a pipeline profile that targets GOES-19 ABI imagery.
profile = PipelineProfile(
    name="goes_search",
    resolution=1000,
    collections={"ABI-L1b-RadF": ["C02"]},
    plugin_hints={"search": "aws_goes"},
    search_params={"satellite": "GOES-19"},
)

# Create a client with the profile and a bounding-box AOI.
client = AereoClient(
    profiles=[profile],
    aoi=box(-70, -40, -68, -39),
)

# Search for assets in a 10-minute window.
results = client.search(
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 10, tzinfo=timezone.utc),
)

print(f"Found {len(results)} assets")
print(results.head())
