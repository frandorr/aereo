# Serverless Local Simulation Example

This directory contains resources to run and test the AEREO Lambda container locally. Using the built-in AWS Lambda Runtime Interface Emulator (RIE), you can test Lambda handler executions with simple HTTP requests without needing to deploy to AWS.

## Prerequisites

- Docker and Docker Compose
- `curl` or `awscurl` for sending test requests
- (Optional) AWS CLI or LocalStack/MinIO for S3 simulation

## Files in this Directory

- `docker-compose.yml`: Set up a local stack containing the Lambda container and a MinIO service simulating S3.
- `sample-event.json`: A mock event payload simulating an incoming task invocation.

## Step-by-Step Local Execution

### 1. Build the Lambda Image

From the root directory of the `aereo` repository, run:

```bash
docker build -f projects/aereo-lambda/Dockerfile -t aereo-lambda:latest .
```

### 2. Launch Local Environment (Lambda RIE + MinIO)

Run the docker-compose stack in this directory:

```bash
docker compose up --build
```

This starts:
- **MinIO** (S3 Emulator) at `http://localhost:9000` (Console at `http://localhost:9001`) with a default bucket named `aereo-local`.
- **Lambda Function** with RIE at `http://localhost:9080/2015-03-31/functions/function/invocations`.

### 3. Stage a Test Task

Before invoking the Lambda, you need to stage a serialized extraction task in S3.

You can use the `aereo` client to stage a task programmatically, pointing to MinIO:

```python
from aereo.client import AereoClient
from aereo.backends import CloudTaskStaging

# Set up local staging pointing to MinIO
staging = CloudTaskStaging(bucket="aereo-local", endpoint_url="http://localhost:9000")
client = AereoClient(staging=staging)

# Stage your tasks...
```

For a simple manual test, we have pre-packaged a mock event in `sample-event.json`.

### 4. Invoke the Lambda Function

Once tasks are staged, invoke the Lambda handler locally using `curl`:

```bash
curl -XPOST "http://localhost:9080/2015-03-31/functions/function/invocations" \
     -d @sample-event.json
```

The emulator will execute `aereo.lambda_handler.core.handler` inside the container and return the JSON response:

```json
{
  "statusCode": 200,
  "manifest_uri": "s3://aereo-local/results/job-123/0/manifest.json",
  "job_id": "job-123",
  "chunk_id": 0
}
```

### 5. Installing Custom Extractor Plugins

To use the Lambda container with a custom extractor (e.g. `odc-stac` or `satpy`), you can modify `projects/aereo-lambda/Dockerfile` to install them from PyPI or copy local wheels:

```dockerfile
# Inside projects/aereo-lambda/Dockerfile, Stage 2:
RUN pip install aereo-extract-odc-stac aereo-extract-satpy
```
