# Run on AWS Lambda

AerEO can run the same `ExtractionJob` on AWS Lambda by swapping the local
executor for `LambdaExecutor`. The pipeline does not change — only the place
where each `ExtractionTask` is executed.

## Why this is serverless

```mermaid
flowchart LR
    subgraph Local["Your laptop / scheduler"]
        Job["ExtractionJob"]
        Tasks["ExtractionTask list"]
        LambdaExec["LambdaExecutor"]
    end

    S3Tasks["S3: staged tasks"] --> Lambda["Lambda function"]
    Lambda --> S3Out["S3: GeoTIFFs + artifacts.parquet"]

    Job --> Tasks
    Tasks --> LambdaExec
    LambdaExec -- stages --> S3Tasks
```

1. You still build the `ExtractionTask` list locally (or in a small launcher).
2. `LambdaExecutor` serialises each task to S3 and invokes one Lambda per task.
3. The Lambda runs the same `read → preprocess → reproject → postprocess → write`
   pipeline stored inside the task.
4. Results are uploaded back to `output_uri`, and the local process collects the
   artifact manifests.

Because the `ExtractionJob`, `ExtractionTask`, and stage functions travel with
the task, the Lambda handler does not need to discover plugins at runtime. You
can develop locally with `LocalExecutor`, then change one line to scale out on
Lambda.

## Swap the executor

```python
from aereo.executors import LambdaExecutor
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")
assets = job.search(...)
tasks = job.build_tasks(assets, build_grouped_tasks)

executor = LambdaExecutor(
    function_name="aereo-extract",
    workers=10,
)
artifacts = job.execute(tasks, executor=executor)
job.write_catalog(artifacts)
```

That is the only code change.

## When to use Lambda

- Large extractions that need more parallelism than your laptop can provide.
- Production pipelines triggered on a schedule or by an event.
- Workloads where you do not want to manage a long-running cluster.

## Cost and tuning tips

- Start with `LocalExecutor` to estimate task runtime and output size.
- Use `cells_per_task` to balance the number of Lambda invocations against the
  work done per invocation.
- Match Lambda memory and timeout to the largest task in your job.
- Enable provisioned concurrency only if you run pipelines on a fixed schedule.

## Packaging

The Lambda function must have AerEO and the same pipeline plugins installed as
your local environment. The repo provides two starting points:

- `aereo-extract` — a Docker-based runtime with HTTP and Lambda handlers. You
  can scaffold a project with `aereo-extract init-docker my-lambda`.
- `projects/aereo-lambda/` — a container image, SAM template, LocalStack setup,
  and integration tests for the older Lambda handler.

See [`projects/aereo-lambda/README.md`](https://github.com/frandorr/aereo/tree/main/projects/aereo-lambda)
for full build, local testing, and SAM deployment instructions.

## Required permissions

The Lambda function needs:

- Read access to the catalog/search APIs you use.
- Write access to the `output_uri` (e.g. an S3 bucket).
- Enough memory and timeout for the largest task in your job.

---

Ready to add your own stage? Head to [Build a Plugin](../plugins/build-a-plugin.md).
