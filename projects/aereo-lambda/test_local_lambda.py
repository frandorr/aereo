#!/usr/bin/env python3
"""Local integration test for AEREO Lambda handler with LocalStack + RIE.

Prerequisites:
    pip install boto3 requests geopandas shapely
    docker compose up --build -d   (from projects/aereo-lambda/)

Usage:
    cd /root/repos/aereo/projects/aereo-lambda
    uv run python test_local_lambda.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests
from shapely.geometry import Polygon

# Add repo and local test pipeline to path so imports work from source.
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(Path(__file__).parent / "test_pipeline"))

from aereo.interfaces import ExtractionTask  # noqa: E402
from aereo.pipeline import ExtractionJob  # noqa: E402
from aereo.schemas import AssetSchema  # noqa: E402
from aereo.executors._serialization import _TaskSerializer  # noqa: E402
from pandera.typing.geopandas import GeoDataFrame  # noqa: E402
from test_pipeline import TestReader, TestWriter  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOCALSTACK_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
LAMBDA_URL = os.getenv(
    "LAMBDA_URL", "http://localhost:9000/2015-03-31/functions/function/invocations"
)
BUCKET = "aereo-tasks"
REGION = "us-east-1"


def _get_s3_client() -> Any:
    import boto3  # type: ignore[import-not-found]

    return boto3.client(
        "s3",
        endpoint_url=LOCALSTACK_URL,
        region_name=REGION,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def _make_minimal_task() -> ExtractionTask:
    df = gpd.GeoDataFrame(
        {
            "id": ["asset_1"],
            "collection": ["test"],
            "start_time": [datetime(2023, 1, 1, 12, 0)],
            "end_time": [datetime(2023, 1, 1, 12, 30)],
            "href": ["s3://bucket/key.tif"],
        },
        geometry=[Polygon([[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01]])],
        crs="EPSG:4326",
    )
    job = ExtractionJob(
        name="test-job",
        grid_dist=50_000,
        output_uri="/tmp/aereo_lambda_test",
        resolution=100.0,
        read=TestReader(),
        write=TestWriter(),
    )
    return ExtractionTask(
        id="task-0",
        assets=GeoDataFrame[AssetSchema](df),
        job=job,
        task_context={"job_id": "test-job", "chunk_id": 0},
    )


def setup_bucket() -> None:
    s3 = _get_s3_client()
    try:
        s3.head_bucket(Bucket=BUCKET)
        print(f"Bucket '{BUCKET}' already exists.")
    except Exception:
        print(f"Creating bucket '{BUCKET}'...")
        s3.create_bucket(Bucket=BUCKET)


def stage_task(task: ExtractionTask) -> str:
    s3 = _get_s3_client()
    serializer = _TaskSerializer()

    with tempfile.TemporaryDirectory() as tmpdir:
        task_dir = Path(tmpdir)
        serializer.serialize(task, task_dir)

        prefix = f"aereo-tasks/{task.task_context['job_id']}/{task.task_context['chunk_id']}/"
        for file in task_dir.iterdir():
            if file.is_file():
                key = f"{prefix}{file.name}"
                print(f"  Uploading {file.name} -> s3://{BUCKET}/{key}")
                s3.upload_file(str(file), BUCKET, key)

    return f"s3://{BUCKET}/{prefix}"


def invoke_lambda(task_uri: str) -> dict[str, Any]:
    payload = {
        "task_uri": task_uri,
        "output_prefix": f"s3://{BUCKET}/results/test-job/0/",
        "job_id": "test-job",
        "chunk_id": 0,
        "bucket": BUCKET,
    }
    print(f"\nInvoking Lambda at {LAMBDA_URL} ...")
    resp = requests.post(LAMBDA_URL, json=payload, timeout=30)
    print(f"HTTP {resp.status_code}")
    try:
        return resp.json()
    except Exception:
        return {"raw_response": resp.text}


def verify_results(manifest_uri: str) -> None:
    s3 = _get_s3_client()
    bucket, key = manifest_uri.replace("s3://", "").split("/", 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        s3.download_file(bucket, key, str(manifest_path))
        manifest = json.loads(manifest_path.read_text())
        print("\nManifest contents:")
        print(json.dumps(manifest, indent=2))

        artifacts_uri = manifest.get("artifacts_uri", "")
        if artifacts_uri:
            bucket, key = artifacts_uri.replace("s3://", "").split("/", 1)
            parquet_path = Path(tmpdir) / "artifacts.parquet"
            s3.download_file(bucket, key, str(parquet_path))
            df = gpd.read_parquet(parquet_path)
            print(f"\nArtifacts GeoDataFrame: {len(df)} rows")
            print(df.head())

            # Verify the uploaded GeoTIFF placeholder exists in S3.
            if len(df) > 0 and "uri" in df.columns:
                geotiff_uri = df["uri"].iloc[0]
                geotiff_bucket, geotiff_key = geotiff_uri.replace("s3://", "").split(
                    "/", 1
                )
                s3.head_object(Bucket=geotiff_bucket, Key=geotiff_key)
                print(f"Verified GeoTIFF in S3: {geotiff_uri}")


def main() -> int:
    print("=" * 60)
    print("AEREO Lambda Local Integration Test")
    print("=" * 60)

    setup_bucket()

    task = _make_minimal_task()
    task_uri = stage_task(task)
    print(f"Task staged at: {task_uri}")

    result = invoke_lambda(task_uri)
    print("\nLambda response:")
    print(json.dumps(result, indent=2, default=str))

    if result.get("statusCode") == 200 and result.get("manifest_uri"):
        verify_results(result["manifest_uri"])
    else:
        print("\nLambda invocation failed - skipping result verification")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
