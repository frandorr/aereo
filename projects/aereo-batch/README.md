# AEREO Batch

AWS Batch execution backend for AEREO satellite data extraction.

## Overview

This project provides:
- `BatchBackend` — An `ExecutionBackend` that dispatches tasks to AWS Batch
- `aereo.batch_handler.core` — Container entrypoint for Batch jobs
- CloudFormation infrastructure for managed EC2 Spot compute

## Architecture

```
AereoClient
    └── BatchBackend
            ├── Serializes tasks to S3
            ├── Submits AWS Batch array jobs
            ├── Polls for completion
            └── Downloads results from S3
```

## Deployment

```bash
cd /root/repos/aereo/projects/aereo-batch
./deploy.sh aereo-batch us-west-2 aereo-batch aereo-batch-tasks
```

## Usage

```python
from aereo.backends import BatchBackend
from aereo.backends.staging import CloudTaskStaging

batch_backend = BatchBackend(
    job_queue="aereo-queue",
    job_definition="aereo-extractor",
    staging=CloudTaskStaging(bucket="aereo-batch-tasks"),
)

client = AereoClient(..., backend=batch_backend)
results = client.execute_tasks(tasks)
```

## Cost

- EC2 Spot instances at ~40% of On-Demand price
- No cost when queue is empty (compute environment scales to 0)
