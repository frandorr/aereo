# Execution Backends

AEREO decouples *what* to extract from *how* to execute. Once you have a list of `ExtractionTask` objects, you choose an **ExecutionBackend** to control parallelism, memory, and remote dispatch.

The default is sequential local execution, but you can swap in process pools, thread pools, or cloud Lambda backends without changing your pipeline code.

---

## Overview

```python
from aereo.client import AereoClient
from aereo.execution import LocalProcessBackend, ThreadBackend

client = AereoClient()

# Assuming 'tasks' was created by client.prepare_for_extraction()

# Sequential (default)
artifacts = client.execute_tasks(tasks)

# Parallel processes — best for CPU-bound extractors (e.g. satpy)
backend = LocalProcessBackend(max_workers=4)
artifacts = client.execute_tasks(tasks, backend=backend)

# Parallel threads — best for I/O-bound extractors (e.g. COG readers)
backend = ThreadBackend(max_workers=8)
artifacts = client.execute_tasks(tasks, backend=backend)
```

---

## `LocalProcessBackend`

Executes tasks locally using `ProcessPoolExecutor` when `max_workers` is set, or sequentially when `None` or only one task is present.

**Best for:** CPU-heavy extractors that release the GIL (satpy, GDAL/rasterio).

```python
from aereo.execution import LocalProcessBackend

backend = LocalProcessBackend(max_workers=4)
artifacts = client.execute_tasks(tasks, backend=backend)
```

Each worker process runs `setup_gdal_worker()` on startup to configure GDAL caching and HTTP multiplexing for remote COG access.

---

## `ThreadBackend`

Executes tasks locally using `ThreadPoolExecutor` when `max_workers` is set.

**Best for:** I/O-bound extractors that spend most of their time waiting on HTTP or S3 (lightweight COG readers, metadata fetching).

```python
from aereo.execution import ThreadBackend

backend = ThreadBackend(max_workers=8)
artifacts = client.execute_tasks(tasks, backend=backend)
```

Threads share memory, so startup overhead is lower than processes. However, CPU-intensive resampling will still contend on the GIL.

---

## `LambdaBackend`

Dispatches tasks to an AWS Lambda function for serverless extraction.

**Best for:** Burst workloads, large-scale parallel extraction, or offloading heavy processing from local machines.

```python
from aereo.backends import CloudTaskStaging, LambdaBackend

backend = LambdaBackend(
    function_name="aereo-extract",
    staging=CloudTaskStaging(bucket="my-staging-bucket"),
)
artifacts = client.execute_tasks(tasks, backend=backend)
```

### How it works

1. **Serialize** each `ExtractionTask` to GeoParquet + JSON via `TaskSerializer`
2. **Stage** serialized files to S3 via `TaskStaging`
3. **Invoke** Lambda with the S3 URI for each task
4. **Poll** for completion and download the result manifest
5. **Load** artifacts from the manifest into a `GeoDataFrame`

### Local emulation

Point `LambdaBackend` at a local Lambda emulator (e.g. Floci):

```python
backend = LambdaBackend(
    function_name="aereo-extract",
    staging=CloudTaskStaging(bucket="local-bucket"),
    endpoint_url="http://localhost:9001",
)
```

---

## `TaskRunner`

`TaskRunner` is the bridge between backends and plugins. You rarely instantiate it directly — `AereoClient.execute_tasks()` creates one automatically — but it is the unit that:

1. Resolves the correct extractor plugin for each task
2. Merges per-task parameters from the profile
3. Calls `extractor.extract(task, params)`

Resolution order:
1. `task.task_context["extractor_hint"]` (highest priority)
2. `task.profile.plugin_hints["extract"]`
3. Auto-discover from `task.profile.collections`

---

## Writing a Custom Backend

Any class implementing the `ExecutionBackend` Protocol can be used:

```python
from typing import Iterable, Sequence
from aereo.execution import ExecutionBackend, TaskRunner
from aereo.interfaces import ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame

class MyBackend:
    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: TaskRunner,
    ) -> Iterable[GeoDataFrame[ArtifactSchema]]:
        for task in tasks:
            yield runner.run(task)
```

Return an `Iterable` so callers can stream results as they arrive.

---

## Failure Modes

Both backends respect `failure_mode`:

| Mode | Behavior |
|------|----------|
| `STRICT` (default) | Re-raise the first exception. |
| `BEST_EFFORT` | Return an empty `GeoDataFrame` on failure. |

Note: in parallel backends, a single failing task currently aborts the entire batch. Per-task failure recovery is on the roadmap.
