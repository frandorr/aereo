# Client API

`AerClient` is the single entry point for almost all AER workflows. Create one instance and call `search()`, `prepare_for_extraction()`, and `extract_batches()` in sequence. The sections below document every parameter and return type.

```python
from aer.client import AerClient

client = AerClient()

results = client.search(profiles=[...], intersects=aoi)
tasks = client.prepare_for_extraction(results, target_aoi=aoi)
artifacts = client.extract_batches(tasks)
```

For a hands-on introduction, see [Quick Start](../quickstart.md) or [Running the Pipeline](../pipeline.md).

::: aer.client
