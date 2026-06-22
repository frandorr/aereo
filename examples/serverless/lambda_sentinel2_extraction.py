#!/usr/bin/env python3
"""Sentinel-2 extraction via AWS Lambda — reproduces 01-sentinel2.ipynb serverlessly.

This script mirrors the local Sentinel-2 notebook workflow but routes each
prepared extraction task through :class:`~aereo.backends.LambdaBackend`.
The Lambda handler executes the task and stores resulting GeoTIFF artifacts
plus a Parquet metadata catalog in the configured S3 bucket.

Prerequisites:
    - An AWS account and credentials configured (``aws configure``), *or* a
      local Lambda Runtime Interface Emulator (RIE) endpoint set via
      ``LAMBDA_URL``.
    - The AEREO Lambda function deployed (see ``projects/aereo-lambda/DEPLOYMENT_DETAILED.md``).
    - ``boto3`` installed (``uv pip install boto3`` or ``pip install boto3``),
      unless testing locally through ``LAMBDA_URL``.

Examples:
    AWS::

        cd /root/repos/aereo
        uv run python examples/serverless/lambda_sentinel2_extraction.py

    Local RIE (after ``docker compose up`` in ``projects/aereo-lambda``)::

        cd /root/repos/aereo
        LAMBDA_URL=http://localhost:9050/2015-03-31/functions/function/invocations \
            AWS_ENDPOINT_URL=http://localhost:4566 \
            uv run python examples/serverless/lambda_sentinel2_extraction.py
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from aereo.backends import LambdaBackend
from aereo.backends.staging import CloudTaskStaging
from aereo.client import AereoClient
from aereo.pipeline import ExtractionJob


@contextmanager
def _chdir(path: Path) -> Generator[None, None, None]:
    """Temporarily change the working directory."""
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def main() -> int:
    """Run the Sentinel-2 notebook workflow through Lambda."""
    # The notebook loads configs relative to the examples/ directory; mirror that
    # so target_aoi and search intersects paths resolve correctly.
    example_dir = Path(__file__).resolve().parent.parent
    with _chdir(example_dir):
        # -------------------------------------------------------------------
        # 1. Load the same config used by examples/01-sentinel2.ipynb
        # -------------------------------------------------------------------
        job = ExtractionJob.load_from_config(
            config_dir="config",
            config_name="job_sentinel2",
        )

    # -----------------------------------------------------------------------
    # 2. Configure S3 staging and the Lambda execution backend
    # -----------------------------------------------------------------------
    bucket = os.getenv("AEREO_S3_BUCKET", "aereo-tasks")
    function_name = os.getenv("AEREO_LAMBDA_FUNCTION", "aereo-extractor")
    endpoint_url = os.getenv("AWS_ENDPOINT_URL") or None  # e.g. LocalStack / MinIO
    lambda_url = os.getenv("LAMBDA_URL") or None  # e.g. RIE direct URL

    # The RIE (Lambda Runtime Interface Emulator) used for local testing can only
    # handle one concurrent invocation; serialise invocations when LAMBDA_URL is set.
    max_concurrent = 1 if lambda_url else 10

    staging = CloudTaskStaging(bucket=bucket, endpoint_url=endpoint_url)
    backend = LambdaBackend(
        function_name=function_name,
        staging=staging,
        endpoint_url=endpoint_url,
        lambda_url=lambda_url,
        max_concurrent_invokes=max_concurrent,
    )

    # -----------------------------------------------------------------------
    # 3. Create a client that uses Lambda for execution
    # -----------------------------------------------------------------------
    client = AereoClient(backend=backend)

    # -----------------------------------------------------------------------
    # 4. Search for Sentinel-2 scenes (same call as the notebook)
    # -----------------------------------------------------------------------
    if job.search is None:
        raise ValueError("Loaded ExtractionJob has no search provider.")

    print("Searching for Sentinel-2 L2A assets...")
    search_results = client.search(job.search)
    print(f"Found {len(search_results)} asset rows")

    if search_results.empty:
        print("No assets found; exiting.")
        return 0

    # -----------------------------------------------------------------------
    # 5. Prepare extraction tasks (same call as the notebook)
    # -----------------------------------------------------------------------
    print("\nPreparing extraction tasks...")
    tasks = client.prepare_tasks(
        search_results=search_results,
        job=job,
        cells_per_task=5,
    )
    print(f"Prepared {len(tasks)} task(s)")

    if not tasks:
        print("No tasks prepared; exiting.")
        return 0

    # -----------------------------------------------------------------------
    # 6. Execute via Lambda (artifacts are stored in S3 by the handler)
    # -----------------------------------------------------------------------
    print(f"\nExecuting {len(tasks)} task(s) via Lambda '{function_name}'...")
    artifacts = client.execute_tasks(tasks)
    print(f"Extracted {len(artifacts)} artifact(s)")

    # -----------------------------------------------------------------------
    # 7. Inspect results
    # -----------------------------------------------------------------------
    if len(artifacts) > 0:
        print("\nResult columns:", list(artifacts.columns))
        print("\nFirst artifacts:")
        print(artifacts.head())
        print(f"\nArtifacts stored in S3 bucket: s3://{bucket}/results/")
    else:
        print("\nNo artifacts were produced.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
