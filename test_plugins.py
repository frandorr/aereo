import pluggy
import pandas as pd
from datetime import datetime, timezone
from shapely.geometry import Polygon

from aer.plugin import AerSpec, PROJECT_NAME
from aer.temporal import TimeRange
from aer.search_aws_goes.core import AwsGoesSearchPlugin
from aer.search_earthaccess.core import EarthAccessSearchPlugin

# 1. Initialize the Pluggy Plugin Manager
pm = pluggy.PluginManager(PROJECT_NAME)
pm.add_hookspecs(AerSpec)

# 2. Discover and load all installed aer plugins dynamically
# Using manual registration to skip the broken extract plugin (being refactored).
# pm.load_setuptools_entrypoints("aer.plugins")

pm.register(AwsGoesSearchPlugin())
pm.register(EarthAccessSearchPlugin())

# 3. Define the query constraints
time_range = TimeRange(
    start=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    end=datetime(2026, 1, 2, 12, 30, tzinfo=timezone.utc),
)

# Optional: define your bounding area of interest (e.g. US Gulf Coast)
intersects = Polygon([(-95, 25), (-80, 25), (-80, 35), (-95, 35), (-95, 25)])

# 4. Trigger the multi-plugin Search
results_list = pm.hook.search(
    collections=["ABI-L1b-RadF", "VJ102IMG"],
    intersects=intersects,
    time_range=time_range,
    search_params={"satellites": ["GOES-19"], "channels": ["C01"]},
)

# 5. Process the outputs
valid_results = [gdf for gdf in results_list if not gdf.empty]

if valid_results:
    combined_gdf = pd.concat(valid_results, ignore_index=True)
    print(f"Found {len(combined_gdf)} total granules.")
    print(combined_gdf[["id", "collection", "start_time", "href"]].head())
else:
    print("No granules found for the specified query.")
