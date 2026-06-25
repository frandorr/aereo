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
from typing import Any, Generator

import geopandas as gpd
import hydra
import pandas as pd
from aereo.backends import LambdaBackend
from aereo.backends.staging import CloudTaskStaging
from aereo.interfaces import SearchProvider, TaskBuilder
from aereo.pipeline import ExtractionJob
from hydra import compose, initialize_config_dir


@contextmanager
def _chdir(path: Path) -> Generator[None, None, None]:
    """Temporarily change the working directory."""
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def _load_job_and_plugins(
    config_dir: Path,
    config_name: str = "job_sentinel2",
) -> tuple[ExtractionJob, SearchProvider, TaskBuilder]:
    """Load a validated ``ExtractionJob`` plus search/task-builder plugins."""
    with initialize_config_dir(version_base=None, config_dir=str(config_dir)):
        cfg = compose(config_name=config_name)
        instantiated = hydra.utils.instantiate(cfg, _convert_="all")

    if not isinstance(instantiated, dict):
        raise ValueError(
            f"Expected Hydra to produce a dict, got {type(instantiated).__name__}"
        )

    job_kwargs: dict[str, Any] = dict(instantiated)
    search_provider = job_kwargs.pop("search", None)
    task_builder = job_kwargs.pop("task_builder", None)

    if search_provider is None:
        raise ValueError("Loaded config is missing a search provider.")
    if task_builder is None:
        raise ValueError("Loaded config is missing a task builder.")

    job = ExtractionJob(**job_kwargs)
    return job, search_provider, task_builder


def main() -> int:
    """Run the Sentinel-2 notebook workflow through Lambda."""
    # The notebook loads configs relative to the examples/ directory; mirror that
    # so target_aoi and search intersects paths resolve correctly.
    example_dir = Path(__file__).resolve().parent.parent
    with _chdir(example_dir):
        job, search_provider, task_builder = _load_job_and_plugins(
            config_dir=Path("config"),
            config_name="job_sentinel2",
        )

    # -----------------------------------------------------------------------
    # Configure S3 staging and the Lambda execution backend
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
    # Search for Sentinel-2 scenes
    # -----------------------------------------------------------------------
    print("Searching for Sentinel-2 L2A assets...")
    search_results = job.search(search_provider)
    print(f"Found {len(search_results)} asset rows")

    if search_results.empty:
        print("No assets found; exiting.")
        return 0

    # -----------------------------------------------------------------------
    # Prepare extraction tasks
    # -----------------------------------------------------------------------
    print("\nPreparing extraction tasks...")
    tasks = job.build_tasks(search_results, task_builder)
    print(f"Prepared {len(tasks)} task(s)")

    if not tasks:
        print("No tasks prepared; exiting.")
        return 0

    # -----------------------------------------------------------------------
    # Execute via Lambda (artifacts are stored in S3 by the handler)
    # -----------------------------------------------------------------------
    print(f"\nExecuting {len(tasks)} task(s) via Lambda '{function_name}'...")
    result_frames = list(backend.run_tasks(tasks))
    if result_frames:
        artifacts = gpd.GeoDataFrame(
            pd.concat(result_frames, ignore_index=True), geometry="geometry"
        )
    else:
        artifacts = gpd.GeoDataFrame()
    print(f"Extracted {len(artifacts)} artifact(s)")

    # -----------------------------------------------------------------------
    # Inspect results
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
