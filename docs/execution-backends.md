# Execution Backends

AEREO decouples *what* to extract from *how* to execute. Once you have a list of `ExtractionTask` objects, you choose an **ExecutionBackend** to control parallelism, memory, and remote dispatch.

The default is sequential local execution, but you can swap in process pools, thread pools, or cloud Lambda backends without changing your pipeline code.

---

## Overview

```python
from aereo.client import AereoClient
from aereo.backends import LocalProcessBackend, ThreadBackend

# Sequential (default)
client = AereoClient()
artifacts = client.execute_tasks(tasks)

# Parallel processes — best for CPU-bound extractors (e.g. satpy)
client = AereoClient(backend=LocalProcessBackend(max_workers=4))
artifacts = client.execute_tasks(tasks)

# Parallel threads — best for I/O-bound extractors (e.g. COG readers)
client = AereoClient(backend=ThreadBackend(max_workers=8))
artifacts = client.execute_tasks(tasks)
```

---

## `LocalProcessBackend`

Executes tasks locally using `ProcessPoolExecutor` when `max_workers` is set, or sequentially when `None` or only one task is present.

**Best for:** CPU-heavy extractors that release the GIL (satpy, GDAL/rasterio).

```python
from aereo.backends import LocalProcessBackend

client = AereoClient(backend=LocalProcessBackend(max_workers=4))
artifacts = client.execute_tasks(tasks)
```

Each worker process runs `setup_gdal_worker()` on startup to configure GDAL caching and HTTP multiplexing for remote COG access.

---

## `ThreadBackend`

Executes tasks locally using `ThreadPoolExecutor` when `max_workers` is set.

**Best for:** I/O-bound extractors that spend most of their time waiting on HTTP or S3 (lightweight COG readers, metadata fetching).

```python
from aereo.backends import ThreadBackend

client = AereoClient(backend=ThreadBackend(max_workers=8))
artifacts = client.execute_tasks(tasks)
```

Threads share memory, so startup overhead is lower than processes. However, CPU-intensive resampling will still contend on the GIL.

---

## `TaskStaging`

When you use a **remote** execution backend such as `LambdaBackend`, the local machine must:

1. Upload the task data so the remote worker can access it.
2. Tell the remote worker where to write its results.
3. Download the results once the worker is done.

`TaskStaging` is the protocol that handles this data movement. It is an **interface** (a Python `Protocol`); you provide a concrete implementation for the object store you are using (e.g. S3, GCS, Azure Blob). Local backends (`LocalProcessBackend`, `ThreadBackend`) do **not** use staging because everything stays on the same machine.

### The protocol

A class that satisfies `TaskStaging` must implement three methods and expose a `bucket` attribute:

| Attribute / Method | Signature | Purpose |
|---|---|---|
| `bucket` | `str` | Name of the target storage bucket / container. |
| `stage` | `(src_dir: Path, job_id: str, task_idx: int) -> str` | Upload the contents of `src_dir` (produced by `TaskSerializer`) and return a URI the remote worker can read. |
| `result_prefix` | `(job_id: str, task_idx: int) -> str` | Return a URI prefix telling the remote worker **where** to write its output. |
| `load_artifacts` | `(manifest_uri: str) -> GeoDataFrame[ArtifactSchema]` | Given the manifest URI returned by the remote worker, download the artifacts and return a validated `GeoDataFrame`. |

### What happens during a remote run

For each task, the backend performs this exact sequence:

```text
1. Serialize task  →  tmp_dir (task_assets.parquet + task_meta.json)
2. staging.stage(tmp_dir, job_id, task_idx)  →  task_uri
3. staging.result_prefix(job_id, task_idx)   →  output_prefix
4. Invoke remote worker with {task_uri, output_prefix}
5. Remote worker writes results to output_prefix and returns a manifest_uri
6. staging.load_artifacts(manifest_uri)      →  GeoDataFrame result
```

### Minimal example: S3 staging

Here is a complete, copy-pasteable implementation using `boto3`:

```python
import boto3
from pathlib import Path
from aereo.execution.core import TaskStaging
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


class S3TaskStaging(TaskStaging):
    """Upload tasks to S3 and download result artifacts."""

    bucket: str

    def __init__(self, bucket: str):
        self.bucket = bucket
        self._s3 = boto3.client("s3")

    def stage(self, src_dir: Path, job_id: str, task_idx: int) -> str:
        """Upload serialized task files and return an S3 URI."""
        prefix = f"aer-tasks/{job_id}/{task_idx}/"
        for file_path in src_dir.iterdir():
            if file_path.is_file():
                key = f"{prefix}{file_path.name}"
                self._s3.upload_file(str(file_path), self.bucket, key)
        return f"s3://{self.bucket}/{prefix}"

    def result_prefix(self, job_id: str, task_idx: int) -> str:
        """Return the S3 prefix where the remote worker should write results."""
        return f"s3://{self.bucket}/aer-results/{job_id}/{task_idx}/"

    def load_artifacts(self, manifest_uri: str) -> GeoDataFrame[ArtifactSchema]:
        """Download the result manifest and load the artifact GeoDataFrame.

        In a real implementation you would:
          1. Parse the JSON manifest.
          2. Download the referenced parquet / GeoJSON files.
          3. Concatenate them into a single GeoDataFrame.
        """
        # Placeholder — replace with real download logic
        return ArtifactSchema.empty()
```

You can now pass this staging object to `LambdaBackend`:

```python
from aereo.execution import LambdaBackend

backend = LambdaBackend(
    function_name="aer-extract",
    staging=S3TaskStaging(bucket="my-staging-bucket"),
)
```

## `LambdaBackend`

Dispatches tasks to an AWS Lambda function for serverless extraction.

**Best for:** Burst workloads, large-scale parallel extraction, or offloading heavy processing from local machines.

```python
from aereo.execution import LambdaBackend

backend = LambdaBackend(
    function_name="aer-extract",
    staging=S3TaskStaging(bucket="my-staging-bucket"),
)
artifacts = client.execute_tasks(tasks)
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
    function_name="aer-extract",
    staging=S3TaskStaging(bucket="local-bucket"),
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
from aereo.backends import ExecutionBackend, TaskRunner
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
