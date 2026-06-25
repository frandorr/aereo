# Run on AWS Lambda

AEREO can dispatch `ExtractionTask` objects to an AWS Lambda function for
serverless, burst-parallel extraction. This is useful when you have many grid
cells or heavy resampling work and want to offload it from your local machine.

---

## Architecture

```text
Your machine                          AWS Lambda
┌─────────────────┐                   ┌─────────────────┐
│ ExtractionJob   │  1. Serialize     │ Lambda handler  │
│ build_tasks()   │ ──▶ task assets   │ receives task   │
│                 │    + metadata     │                 │
└─────────────────┘                   └─────────────────┘
        │                                    │
        │ 2. Upload to S3                  3. Download from S3
        │                                    │
        │ 4. Invoke Lambda                 5. Run extraction stages
        │                                    │
        │ 6. Receive result                7. Write results to S3
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
from aereo.executors import LambdaExecutor
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

results = job.search(...)
tasks = job.build_tasks(results, ...)

executor = LambdaExecutor(
    function_name="aereo-extract",
    staging_bucket="my-staging-bucket",
)

artifacts = job.execute(tasks, executor=executor)
print(f"Extracted {len(artifacts)} artifacts")
```

`LambdaExecutor` handles task serialization, S3 staging, invocation,
manifest loading, and result concatenation internally.

---

## How staging works

Remote execution needs a way to move serialized tasks and results to and from
S3. `LambdaExecutor` uses an internal staging helper that uploads tasks to
`s3://<staging_bucket>/aereo-tasks/<job_id>/<chunk_id>/` and tells the Lambda
handler to write results to a matching prefix under the same bucket.

You do not need to implement a staging protocol yourself; just provide the
bucket name. If you need a custom storage backend for loading result manifests,
pass a `StorageBackend` to the `storage` argument.

---

## Local emulation

Point `LambdaExecutor` at a local Lambda emulator or LocalStack for testing:

```python
executor = LambdaExecutor(
    function_name="aereo-extract",
    staging_bucket="local-bucket",
    endpoint_url="http://localhost:4566",
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

For most first-time users, `LocalExecutor` is the right choice. Move to Lambda
once you understand your task size and cost profile.
