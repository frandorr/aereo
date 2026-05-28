# aereo-lambda

AEREO Lambda container image — packages the AWS Lambda handler and AEREO core bricks for serverless extraction tasks.

## Overview

The Lambda handler at `aereo.lambda_handler.core.handler` receives a single `ExtractionTask`, executes it via the local plugin registry, and stores results in S3. It is designed for the remote-execution backend (`LambdaBackend`) which serializes tasks to S3 and invokes one Lambda per task.

### What it does

1. **Deserialize** — Downloads a serialized `ExtractionTask` from S3 (GeoParquet + JSON)
2. **Execute** — Runs `TaskRunner` which resolves the correct extractor plugin and calls `extract()`
3. **Store** — Uploads the resulting `GeoDataFrame[ArtifactSchema]` as a Parquet file + manifest JSON back to S3

### What it does NOT do (current limitations)

- **Direct GeoTIFF return**: The architecture enforces `Extractor.extract()` → `GeoDataFrame[ArtifactSchema]` → Parquet → S3 manifest. It cannot return raw GeoTIFF bytes in the Lambda response. See [GeoTIFF Return Options](#geotiff-return-options) for alternatives.

---

## Build

```bash
cd /root/repos/aereo
uv build --wheel projects/aereo-lambda
```

Or build the Docker image directly:

```bash
cd /root/repos/aereo
docker build -f projects/aereo-lambda/Dockerfile -t aereo-lambda:latest .
```

---

## Local Testing with Docker Compose (RIE + LocalStack)

The fastest way to test the Lambda locally. Uses:

- **LocalStack** — emulates S3 on `localhost:4566`
- **Lambda RIE** (Runtime Interface Emulator) — runs the Lambda handler on `localhost:9000`

### Prerequisites

- Docker + Docker Compose
- `uv` (for running the test script)

### Start services

```bash
cd projects/aereo-lambda
docker compose up --build -d
```

This starts two containers:

| Service | Port | Description |
|---------|------|-------------|
| `localstack` | `4566` | S3 emulation |
| `aereo-lambda` | `9000` | Lambda RIE (maps container port `8080`) |

### Run the integration test

The test script creates a bucket, stages a sample `ExtractionTask` with a test extractor plugin, and invokes the Lambda:

```bash
cd projects/aereo-lambda
uv run python test_local_lambda.py
```

Expected output:

```
============================================================
AEREO Lambda Local Integration Test
============================================================
Creating bucket 'aereo-tasks'...
  Uploading task_meta.json -> s3://aereo-tasks/aereo-tasks/test-job/0/task_meta.json
  Uploading task_assets.parquet -> s3://aereo-tasks/aereo-tasks/test-job/0/task_assets.parquet
Task staged at: s3://aereo-tasks/aereo-tasks/test-job/0/

Invoking Lambda at http://localhost:9000/2015-03-31/functions/function/invocations ...
HTTP 200

Lambda response:
{
  "statusCode": 200,
  "manifest_uri": "s3://aereo-tasks/results/test-job/0/manifest.json",
  "job_id": "test-job",
  "chunk_id": 0
}

Manifest contents:
{
  "artifacts_uri": "s3://aereo-tasks/results/test-job/0/artifacts.parquet"
}

Artifacts GeoDataFrame: 0 rows
```

### Manual invocation with curl

```bash
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -H "Content-Type: application/json" \
  -d @events/extraction-task.json
```

### Stop services

```bash
docker compose down -v
```

---

## Architecture

### Lambda Handler Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Event JSON    │     │  S3 Download     │     │  Extractor      │
│  (task_uri)     │────▶│  (task_assets    │────▶│  Plugin         │
│                 │     │   + task_meta)   │     │  (TaskRunner)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Response JSON  │◄────│  S3 Upload       │◄────│  GeoDataFrame   │
│  (manifest_uri) │     │  (artifacts      │     │  [ArtifactSchema]│
│                 │     │   + manifest)    │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### Event Payload Format

The handler expects a JSON payload with these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_uri` | string | ✅ | S3 URI prefix where the serialized `ExtractionTask` is staged |
| `output_prefix` | string | ✅ | S3 URI prefix where results should be written |
| `job_id` | string | ✅ | Logical job identifier |
| `chunk_id` | int | ✅ | Task index within the job |
| `bucket` | string | ❌ | S3 bucket name; inferred from `task_uri` if omitted |
| `init_params` | dict | ❌ | Constructor kwargs for extractor instantiation |

Example: `events/extraction-task.json`

### Serialization Format

The `TaskSerializer` writes each `ExtractionTask` as two files in a directory:

- `task_assets.parquet` — GeoParquet of the task's `assets` GeoDataFrame
- `task_meta.json` — JSON with profile, grid config, cells, URI, AOI, and task context

### Result Format

The Lambda uploads two files to `output_prefix`:

- `artifacts.parquet` — GeoDataFrame of extracted artifacts (`ArtifactSchema`)
- `manifest.json` — `{"artifacts_uri": "s3://bucket/results/job/task/artifacts.parquet"}`

The handler returns JSON:

```json
{
  "statusCode": 200,
  "manifest_uri": "s3://bucket/results/job/task/manifest.json",
  "job_id": "test-job",
  "chunk_id": 0
}
```

---

## Local Testing with SAM CLI

If you have the AWS SAM CLI installed, you can also test with `sam local invoke`.

### Prerequisites

- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Docker image built (`aereo-lambda:latest`)

### Invoke locally

```bash
cd projects/aereo-lambda
sam local invoke AereoLambdaFunction --event events/extraction-task.json
```

### Start local API (optional)

```bash
sam local start-api
```

Then POST to `http://localhost:3000/invoke`.

---

## Using Real Extractor Plugins

The test setup includes a minimal `test_extractor` plugin that returns an empty `GeoDataFrame`. To test with a real extractor (e.g., `extract_satpy` for GOES data), you need to install the plugin in the Lambda container.

### Option 1: Install from PyPI (production)

Uncomment in the Dockerfile:

```dockerfile
RUN pip install aereo-extract-satpy aereo-extract-odc-stac
```

### Option 2: Mount local plugin repos (development)

If you have plugin repos cloned locally (e.g., `aereo-extract-satpy`), mount them in `docker-compose.yml`:

```yaml
services:
  aereo-lambda:
    volumes:
      - /path/to/aereo-extract-satpy:/opt/aereo-extract-satpy
    environment:
      - PYTHONPATH=/opt/aereo-extract-satpy/bases:/opt/aereo-extract-satpy/components
```

### Option 3: Build plugins into the image (monorepo)

Copy plugin wheels into the Docker image alongside the main AEREO wheels. See the builder stage in the Dockerfile for the pattern.

### Plugin Discovery

Plugins are discovered via Python entry points (`aereo.plugins` group). The Lambda container's `AereoRegistry` scans for these on cold start. Verify installed plugins:

```bash
docker exec aereo-lambda-aereo-lambda-1 python -c "
import importlib.metadata
for ep in importlib.metadata.entry_points(group='aereo.plugins'):
    print(f'{ep.name}: {ep.value}')
"
```

---

## GeoTIFF Return Options

The current Lambda handler **cannot** return a GeoTIFF directly because:

1. `Extractor.extract()` contract returns `GeoDataFrame[ArtifactSchema]`
2. The handler always serializes that to Parquet + uploads to S3
3. The response is JSON with a `manifest_uri`, not binary data

### Workarounds

| Approach | Pros | Cons |
|----------|------|------|
| **Base64 in JSON** | Simple, no S3 needed | 6MB Lambda payload limit; slow |
| **Pre-signed S3 URL** | No payload limit; caller streams directly | Requires S3; extra request |
| **Separate handler** | Clean separation; can return any format | More code to maintain |

### Pre-signed URL approach (recommended)

Add a step after extraction that generates a pre-signed URL for the uploaded GeoTIFF and includes it in the JSON response:

```python
# In handler, after upload:
url = s3.generate_presigned_url(
    "get_object",
    Params={"Bucket": bucket, "Key": geotiff_key},
    ExpiresIn=3600,
)
return {
    "statusCode": 200,
    "manifest_uri": manifest_uri,
    "download_url": url,
}
```

---

## Files

| File | Description |
|------|-------------|
| `Dockerfile` | Multi-stage build: Hatch builder + Lambda runtime |
| `docker-compose.yml` | LocalStack + Lambda RIE orchestration |
| `template.yaml` | SAM template for `sam local invoke` |
| `events/extraction-task.json` | Sample Lambda event payload |
| `test_local_lambda.py` | End-to-end integration test script |
| `test_extractor/` | Minimal extractor plugin for testing |

---

## Troubleshooting

### "No extractor plugin found for profile"

The extractor hint in the profile doesn't match any registered plugin. Check:

1. Plugin is installed in the Lambda container (`pip list | grep aereo`)
2. Entry point is registered (`python -c "import importlib.metadata; ..."`)
3. Profile's `plugin_hints.extract` matches the entry point name

### "Missing optional dependency 'pyarrow.parquet'"

The Lambda runtime was missing `pyarrow`. Fixed by adding it to `pyproject.toml` dependencies.

### LocalStack license error

Use `localstack/localstack:3` (community edition) instead of `:latest` (which may require a Pro license).

### SAM CLI "No such image"

Build the Docker image first:

```bash
cd /root/repos/aereo
docker build -f projects/aereo-lambda/Dockerfile -t aereo-lambda:latest .
```

---

## Development Notes

- The Lambda handler initializes `AereoRegistry` and `TaskRunner` at module load time (cold start optimization)
- Memory errors are re-raised so the Lambda runtime can handle them
- All other errors are caught, logged with `structlog`, and returned as JSON with `retryable` flag
- `boto3` is imported lazily so the handler can be imported without AWS SDK installed

---

## Related

- [AEREO Client Documentation](../aereo/README.md)
- [Extraction Examples](../../examples/extraction/)
- [Plugin Creator Skill](../../.agents/skills/plugin-creator/SKILL.md)
