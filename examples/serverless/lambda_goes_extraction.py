#!/usr/bin/env python3
"""
Lambda GOES Extraction Example

This example runs the minimal GOES extraction workflow using the AWS Lambda
backend. Results are stored in S3.

Prerequisites:
    - AWS Lambda deployed (see DEPLOYMENT.md)
    - AWS credentials configured
    - boto3 installed

Usage:
    cd /root/repos/aereo
    uv run python examples/serverless/lambda_goes_extraction.py
"""

from datetime import datetime, timezone

from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig
from aereo.backends import LambdaBackend
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
# 2. Configure Lambda backend with S3 staging
# ---------------------------------------------------------------------------
# NOTE: Update these values if you deployed with different names
BUCKET = "frandorr-lambda-tests"
FUNCTION_NAME = "aereo-extractor"
REGION = "us-west-2"

staging = CloudTaskStaging(bucket=BUCKET)
lambda_backend = LambdaBackend(
    function_name=FUNCTION_NAME,
    staging=staging,
)

# ---------------------------------------------------------------------------
# 3. Create client with Lambda backend
# ---------------------------------------------------------------------------
client = AereoClient(
    profiles=[profile],
    grid_config=GridConfig(target_grid_dist=256_000),
    aoi=box(-70, -40, -68, -39),
    backend=lambda_backend,
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
    uri="s3://frandorr-lambda-tests/goes-results",
)
print(f"Prepared {len(tasks)} task(s)")

# ---------------------------------------------------------------------------
# 6. Execute tasks via Lambda (results go to S3)
# ---------------------------------------------------------------------------
print(f"Executing {len(tasks)} task(s) via Lambda '{FUNCTION_NAME}'...")
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
    results_df.to_parquet("/tmp/lambda_goes_results.parquet")
    print("Saved result metadata to /tmp/lambda_goes_results.parquet")
else:
    print("No results returned.")

print("\nDone!")
