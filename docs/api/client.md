# Client API

`ExtractionJob` is the single entry point for almost all AEREO workflows. Load
or construct a job, then call `search()`, `build_tasks()`, and `execute()` in
sequence. The sections below document every parameter and return type.

```python
from aereo.builtins import GroupedTaskBuilder, SearchSTAC
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

# Load a Hydra config package (recommended)
job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

results = job.search(SearchSTAC(...))
tasks = job.build_tasks(results, GroupedTaskBuilder())
artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))
```

For a hands-on introduction, see [Your First Pipeline](../first-pipeline.md).

::: aereo.pipeline
