# Client API

`AereoClient` is the single entry point for almost all AEREO workflows. Create one instance and call `search()`, `prepare_for_extraction()`, and `execute_tasks()` in sequence. The sections below document every parameter and return type.

```python
from datetime import datetime, timezone
from shapely.geometry import box
from aereo.client import AereoClient
from aereo.interfaces import AereoProfile
from aereo.backends import LocalProcessBackend

client = AereoClient()

profile = AereoProfile(
    name="goes",
    resolution=1000,
    collections={"ABI-L1b-RadF": ["C01"]},
    plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
    search_params={"satellite": "GOES-19"},
)
aoi = box(-69.76, -39.98, -68.24, -39.05)

results = client.search(
    profiles=[profile],
    intersects=aoi,
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 9, tzinfo=timezone.utc),
)
tasks = client.prepare_for_extraction(results, profiles=[profile], target_aoi=aoi, uri="./out")

backend = LocalProcessBackend()
artifacts = client.execute_tasks(tasks, backend=backend)
```

For a hands-on introduction, see [Your First Pipeline](../first-pipeline.md).

::: aereo.client
