# Client API

`AereoClient` is the single entry point for almost all AEREO workflows. Create
one instance and call `search()`, `build_tasks()`, and `execute_tasks()` in
sequence. The sections below document every parameter and return type.

```python
from aereo.pipeline import ExtractionJob
from aereo.client import AereoClient
from aereo.backends import LocalProcessBackend

client = AereoClient()

# Load a Hydra config package (recommended)
job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

results = client.search(job.search)
tasks = client.build_tasks(results, job=job)

backend = LocalProcessBackend(max_workers=2)
artifacts = client.execute_tasks(tasks, backend=backend)
```

For a hands-on introduction, see [Your First Pipeline](../first-pipeline.md).

::: aereo.client
