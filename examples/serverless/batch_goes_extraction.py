#!/usr/bin/env python3
"""
Batch GOES Extraction Example

This example runs the GOES extraction workflow using the AWS Batch
backend with EC2 Spot instances. Results are stored in S3.

Prerequisites:
    - AWS Batch deployed (see projects/aereo-batch/deploy.sh)
    - AWS credentials configured
    - boto3 installed

Usage:
    cd /root/repos/aereo
    uv run python examples/serverless/batch_goes_extraction.py
"""

from datetime import datetime, timezone

from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig
from aereo.backends import BatchBackend
from aereo.backends.staging import CloudTaskStaging
from shapely.geometry import box

# ---------------------------------------------------------------------------
# 1. Define the extraction profile
# ---------------------------------------------------------------------------
profile = AereoProfile(
    name="goes",
    resolution=1000,
    collections={"ABI-L1b-RadF": ["C02"]},
    plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
    search_params={"satellite": "GOES-19"},
    extract_params={
        "reader": "abi_l1b",
        "calibration": "reflectance",
        "delay_writes": True,
        "download_workers": 4,
    },
)

# ---------------------------------------------------------------------------
# 2. Configure Batch backend with S3 staging
# ---------------------------------------------------------------------------
# NOTE: Update these values if you deployed with different names
BUCKET = "aereo-batch-tasks"
JOB_QUEUE = "aereo-queue"
JOB_DEFINITION = "aereo-extractor"
REGION = "us-west-2"

staging = CloudTaskStaging(bucket=BUCKET)
batch_backend = BatchBackend(
    job_queue=JOB_QUEUE,
    job_definition=JOB_DEFINITION,
    staging=staging,
    region=REGION,
)

# ---------------------------------------------------------------------------
# 3. Create client with Batch backend
# ---------------------------------------------------------------------------
client = AereoClient(
    profiles=[profile],
    grid_config=GridConfig(target_grid_dist=256_000),
    aoi=box(-70, -40, -68, -39),
    backend=batch_backend,
)

# ---------------------------------------------------------------------------
# 4. Search for GOES data
# ---------------------------------------------------------------------------
print("Searching for GOES-19 ABI C02 data...")
results = client.search(
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 10, tzinfo=timezone.utc),
)
print(f"Found {len(results)} assets")

# ---------------------------------------------------------------------------
# 5. Prepare extraction tasks
# ---------------------------------------------------------------------------
print("Preparing extraction tasks...")
tasks = client.prepare_for_extraction(
    results,
    uri=f"s3://{BUCKET}/goes-results",
)
print(f"Prepared {len(tasks)} task(s)")

# ---------------------------------------------------------------------------
# 6. Execute tasks via Batch (results go to S3)
# ---------------------------------------------------------------------------
print(f"Executing {len(tasks)} task(s) via Batch '{JOB_QUEUE}'...")
results_df = client.execute_tasks(tasks)
print(f"Extraction complete! {len(results_df)} artifact(s) returned")

# ---------------------------------------------------------------------------
# 7. Inspect results
# ---------------------------------------------------------------------------
print("\nResults:")
print(results_df.head())

if len(results_df) > 0:
    print(f"\nArtifacts stored in S3 bucket: {BUCKET}")
    print("Result columns:", list(results_df.columns))
    
    # Save result metadata locally
    results_df.to_parquet("/tmp/batch_goes_results.parquet")
    print("Saved result metadata to /tmp/batch_goes_results.parquet")
else:
    print("No results returned.")

print("\nDone!")
