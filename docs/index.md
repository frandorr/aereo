<p align="center">
    <img src="banner.svg" alt="AEREO logo" style="max-width: 300px; width: 100%;">
</p>

<!--<h1 align="center">
  Plugin-based satellite data extraction — from search to analysis-ready Major TOM grid in minutes.
</h1>-->

---

Satellite data lives in a dozen different catalogs, each with its own API, authentication, and file format. **AEREO** unifies them into a single pipeline: **search** across catalogs, **extract** assets, and receive everything reprojected to the same **Major TOM grid** — ready for multi-sensor model training.

<div class="grid cards" markdown>

-   ## Search and Extract

    ---

    Process satellite data with AEREO's unified pipeline.

    [:octicons-arrow-right-24: Get Started](first-pipeline.md)

-   ## Build a Plugin

    ---

    Extend AEREO with custom search and extract plugins.

    [:octicons-arrow-right-24: Learn How](plugin-overview.md)

-   ## API Reference

    ---

    Explore the complete API for power users and plugin developers.

    [:octicons-arrow-right-24: View API](api/client.md)

</div>

---

## 10-line example

```python
from datetime import datetime, timezone
from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig
from shapely.geometry import box

client = AereoClient()
profile = AereoProfile(
    name="goes",
    resolution=1000,
    collections={"ABI-L1b-RadF": ["C01"]},
    plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
    search_params={"satellite": "GOES-19"},
    extract_params={"reader": "abi_l1b"},
)
results = client.search(
    profiles=[profile],
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 10, tzinfo=timezone.utc),
    intersects=box(-70, -40, -68, -39),
)
tasks = client.prepare_for_extraction(
    results,
    profiles=[profile],
    output_uri="./out",
    grid_config=GridConfig(target_grid_dist=256000),
)
client.execute_tasks(tasks)
```

Open `./out/` — you have GeoTIFFs.

---

Apache License 2.0
