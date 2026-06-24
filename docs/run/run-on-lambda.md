# Run on AWS Lambda

AEREO can dispatch `ExtractionTask` objects to an AWS Lambda function for
serverless, burst-parallel extraction. This is useful when you have many grid
cells or heavy resampling work and want to offload it from your local machine.

---

## Architecture

```text
Your machine                          AWS Lambda
┌─────────────────┐                   ┌─────────────────┐
│ AereoClient     │  1. Serialize     │ Lambda handler  │
│ build_tasks() │ ──▶ task assets   │ receives task   │
│                 │    + metadata     │                 │
└─────────────────┘                   └─────────────────┘
        │                                    │
        │ 2. Upload to S3                  3. Download from S3
        │                                    │
        │ 4. Invoke Lambda                 5. Run extraction stages
        │                                    │
        │ 6. Poll / receive result         7. Write results to S3
        │                                    │
        │ 8. Download artifacts            9. Return manifest
        ▼                                    ▼
   GeoDataFrame[ArtifactSchema]  ◀───────────
```

The local machine is responsible for search, prepare, and orchestration. The
Lambda function receives a serialized task, runs the extraction stages, and
writes results back to S3.

---

## Deploy the Lambda function

The Lambda handler lives in `bases/aereo/lambda_handler`. Build and deploy it
like any other Python Lambda package. A minimal example is in
`examples/serverless/`:

```bash
cd examples/serverless
# Review docker-compose.yml and README.md for local emulation
docker compose up
```

For production, package the handler with the plugins it needs and deploy to
AWS Lambda.

---

## Dispatch tasks from Python

```python
from aereo.client import AereoClient
from aereo.backends import LambdaBackend
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")
client = AereoClient()

results = client.search(job.search)
tasks = client.build_tasks(results, job=job)

backend = LambdaBackend(
    function_name="aereo-extract",
    # staging=...,  # see TaskStaging protocol below
)

artifacts = client.execute_tasks(tasks, backend=backend)
print(f"Extracted {len(artifacts)} artifacts")
```

---

## TaskStaging protocol

Remote backends need a way to move serialized tasks and results to and from S3.
AEREO defines this through the `TaskStaging` protocol. You provide a concrete
implementation for your object store.

```python
import boto3
from pathlib import Path
from aereo.interfaces import TaskStaging
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


class S3TaskStaging(TaskStaging):
    """Upload tasks to S3 and download result artifacts."""

    bucket: str

    def __init__(self, bucket: str):
        self.bucket = bucket
        self._s3 = boto3.client("s3")

    def stage(self, src_dir: Path, job_id: str, task_idx: int) -> str:
        prefix = f"aereo-tasks/{job_id}/{task_idx}/"
        for file_path in src_dir.iterdir():
            if file_path.is_file():
                key = f"{prefix}{file_path.name}"
                self._s3.upload_file(str(file_path), self.bucket, key)
        return f"s3://{self.bucket}/{prefix}"

    def result_prefix(self, job_id: str, task_idx: int) -> str:
        return f"s3://{self.bucket}/aereo-results/{job_id}/{task_idx}/"

    def load_artifacts(self, manifest_uri: str) -> GeoDataFrame[ArtifactSchema]:
        # Parse the manifest, download parquet/GeoJSON files, and concatenate.
        # Replace with real S3 download logic.
        return ArtifactSchema.empty()
```

Then pass staging to the backend:

```python
backend = LambdaBackend(
    function_name="aereo-extract",
    staging=S3TaskStaging(bucket="my-staging-bucket"),
)
```

---

## Local emulation

Point `LambdaBackend` at a local Lambda emulator for testing:

```python
backend = LambdaBackend(
    function_name="aereo-extract",
    staging=S3TaskStaging(bucket="local-bucket"),
    endpoint_url="http://localhost:9001",
)
```

See `examples/serverless/` in the repository for a complete local setup with
`docker-compose.yml`.

---

## When to use Lambda

| Use Lambda | Don't use Lambda |
|------------|------------------|
| Many grid cells / burst parallelism | Few cells or fast local extractions |
| Heavy CPU resampling you want offloaded | You need tight iteration in a notebook |
| Production pipelines triggered by events | Prototyping a new sensor |

For most first-time users, `LocalProcessBackend` is the right choice. Move to
Lambda once you understand your task size and cost profile.
