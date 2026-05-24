# Client API

`AerClient` is the single entry point for almost all AER workflows. Create one instance and call `search()`, `prepare_for_extraction()`, and `execute_tasks()` in sequence. The sections below document every parameter and return type.

```python
from aer.client import AerClient

client = AerClient()

results = client.search(profiles=[...], intersects=aoi)
tasks = client.prepare_for_extraction(results, target_aoi=aoi)
from aer.execution import LocalProcessBackend

backend = LocalProcessBackend()
artifacts = client.execute_tasks(tasks, backend=backend)
```

For a hands-on introduction, see [Quick Start](../quickstart.md) or [Running the Pipeline](../pipeline.md).

::: aer.client
