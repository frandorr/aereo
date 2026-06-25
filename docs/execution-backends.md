# Execution Backends

AEREO decouples *what* to extract from *how* to execute. Once you have a list of
`ExtractionTask` objects, you choose an **Executor** to control parallelism,
memory, and remote dispatch.

The default is sequential local execution, but you can swap in process pools,
thread pools, or a cloud Lambda executor without changing your pipeline code.

---

## Overview

```python
from aereo.pipeline import ExtractionJob
from aereo.executors import LocalExecutor

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

results = job.search(...)
tasks = job.build_tasks(results, ...)

# Sequential (default)
artifacts = job.execute(tasks)

# Parallel processes — best for CPU-bound extractors (e.g. satpy)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=4))

# Parallel threads — best for I/O-bound extractors (e.g. COG readers)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=8, use_threads=True))
```

---

## `LocalExecutor`

Executes tasks locally using `ProcessPoolExecutor` when `workers` is greater
than `1`, or sequentially when `workers` is `None` or `1`.

**Best for:** CPU-heavy extractors that release the GIL (satpy, GDAL/rasterio).

```python
from aereo.executors import LocalExecutor

artifacts = job.execute(tasks, executor=LocalExecutor(workers=4))
```

Each worker process runs `setup_gdal_worker()` on startup to configure GDAL
caching and HTTP multiplexing for remote COG access.

### Constructor arguments

| Argument | Type | Default | Description |
|---|---|---|---|
| `workers` | `int \| None` | `1` | Maximum number of parallel workers. `None` or `1` runs sequentially. |
| `failure_mode` | `"strict" \| "best_effort"` | `"strict"` | `"strict"` aborts on the first failure; `"best_effort"` skips failed tasks. |
| `cache` | `TaskResultCache \| None` | `None` | Optional per-task artifact catalog cache. |
| `use_threads` | `bool` | `False` | Use `ThreadPoolExecutor` instead of `ProcessPoolExecutor`. |

---

## `LambdaExecutor`

Dispatches tasks to an AWS Lambda function for serverless extraction.

**Best for:** Burst workloads, large-scale parallel extraction, or offloading
heavy processing from local machines.

```python
from aereo.executors import LambdaExecutor

executor = LambdaExecutor(
    function_name="aereo-extract",
    staging_bucket="my-staging-bucket",
)
artifacts = job.execute(tasks, executor=executor)
```

### Constructor arguments

| Argument | Type | Default | Description |
|---|---|---|---|
| `function_name` | `str` | required | AWS Lambda function name or ARN. |
| `staging_bucket` | `str` | required | S3 bucket used to stage serialized tasks. |
| `storage` | `StorageBackend \| None` | `None` | Optional storage backend for loading result manifests. |
| `failure_mode` | `"strict" \| "best_effort"` | `"strict"` | `"strict"` aborts on the first failure; `"best_effort"` skips failed tasks. |
| `endpoint_url` | `str \| None` | `None` | Optional boto3 endpoint URL (e.g. for LocalStack). |
| `max_concurrent_invokes` | `int` | `10` | Maximum number of concurrent Lambda invocations. |
| `invoke_timeout` | `int` | `900` | Read timeout in seconds for the boto3 Lambda client. |

### How it works

1. **Serialize** each `ExtractionTask` to GeoParquet + JSON via an internal
   serializer.
2. **Stage** serialized files to S3 under `s3://<staging_bucket>/aereo-tasks/...`.
3. **Invoke** Lambda with the staged task URI and output prefix for each task.
4. **Load** artifacts from the manifest URI returned by the Lambda handler.
5. **Concatenate** all per-task artifact GeoDataFrames into a single result.

### Local emulation

Point `LambdaExecutor` at a local Lambda emulator or LocalStack:

```python
executor = LambdaExecutor(
    function_name="aereo-extract",
    staging_bucket="local-bucket",
    endpoint_url="http://localhost:4566",
)
```

---

## The `Executor` protocol

Any callable class that accepts a sequence of `ExtractionTask` objects and
returns a `GeoDataFrame[ArtifactSchema]` can be used as an executor:

```python
from collections.abc import Sequence
from typing import Protocol

from aereo.interfaces import ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


class Executor(Protocol):
    def __call__(
        self,
        tasks: Sequence[ExtractionTask],
    ) -> GeoDataFrame[ArtifactSchema]:
        ...
```

A minimal custom executor looks like this:

```python
from aereo.execution import run_task

class SequentialExecutor:
    def __call__(self, tasks):
        results = []
        for task in tasks:
            results.append(run_task(task))
        return gpd.GeoDataFrame(pd.concat(results, ignore_index=True), geometry="geometry")
```

---

## Failure modes

Both executors respect `failure_mode`:

| Mode | Behavior |
|------|----------|
| `"strict"` (default) | Re-raise the first exception and stop execution. |
| `"best_effort"` | Log the failure, skip the failed task, and return artifacts from successful tasks. |

In parallel mode, a failing task in `"strict"` mode cancels remaining pending
work before the exception is raised.
