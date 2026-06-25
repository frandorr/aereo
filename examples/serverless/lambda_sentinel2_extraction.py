#!/usr/bin/env python3
"""Sentinel-2 extraction via AWS Lambda — reproduces 01-sentinel2.ipynb serverlessly.

This script mirrors the local Sentinel-2 notebook workflow but routes each
prepared extraction task through :class:`~aereo.executors.LambdaExecutor`.
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
from pathlib import Path
from typing import Any

import hydra
from aereo.executors import LambdaExecutor
from aereo.interfaces import SearchProvider, TaskBuilder
from aereo.pipeline import ExtractionJob
from omegaconf import OmegaConf


def _load_job(config_dir: Path, config_name: str = "job_sentinel2") -> ExtractionJob:
    """Load a validated ``ExtractionJob`` from the Hydra config package."""
    return ExtractionJob.load_from_config(config_dir, config_name=config_name)


def _load_plugin(config_dir: Path, group: str, name: str) -> Any:
    """Load a single plugin from a config group file."""
    path = config_dir / group / f"{name}.yaml"
    cfg = OmegaConf.load(path)
    return hydra.utils.instantiate(cfg, _convert_="all")


def _load_plugins(
    config_dir: Path,
    search_name: str = "sentinel2_pc",
    task_builder_name: str = "grouped",
) -> tuple[SearchProvider, TaskBuilder]:
    """Load search provider and task builder plugins from the config package."""
    search_provider = _load_plugin(config_dir, "search", search_name)
    task_builder = _load_plugin(config_dir, "task_builder", task_builder_name)
    return search_provider, task_builder


def main() -> int:
    """Run the Sentinel-2 notebook workflow through Lambda."""
    # The notebook loads configs relative to the examples/ directory; mirror that
    # so target_aoi and search intersects paths resolve correctly.
    example_dir = Path(__file__).resolve().parent.parent
    config_dir = example_dir / "config"

    job = _load_job(config_dir=config_dir, config_name="job_sentinel2")
    search_provider, task_builder = _load_plugins(
        config_dir,
        search_name="sentinel2_pc",
        task_builder_name="grouped",
    )

    # -----------------------------------------------------------------------
    # Configure the Lambda execution backend
    # -----------------------------------------------------------------------
    bucket = os.getenv("AEREO_S3_BUCKET", "aereo-tasks")
    function_name = os.getenv("AEREO_LAMBDA_FUNCTION", "aereo-extractor")
    endpoint_url = os.getenv("AWS_ENDPOINT_URL") or None  # e.g. LocalStack / MinIO

    executor = LambdaExecutor(
        function_name=function_name,
        staging_bucket=bucket,
        endpoint_url=endpoint_url,
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
    artifacts = job.execute(tasks, executor=executor)
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
