"""Tests for aereo_extract handlers."""

from __future__ import annotations

import base64
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import geopandas as gpd
from aereo_extract.handlers import handle_event, handle_lambda
from aereo.grid import ExtractionPatch
from aereo.interfaces import ExtractConfig, ExtractionTask, GridConfig, PatchConfig
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from aereo.serialization import TaskSerializer
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


def _make_task() -> ExtractionTask:
    """Return a minimal extraction task with a test pipeline."""
    from test_pipeline import TestReader, TestReprojector, TestWriter

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
    patch = ExtractionPatch(
        id="0U_0R",
        d=50_000,
        cell_geometry=Polygon([[0, 0], [0.005, 0], [0.005, 0.005], [0, 0.005]]),
        resolution=100.0,
        margin=0.0,
        padding=0,
    )
    job = ExtractionJob(
        name="test-job",
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=100.0),
        output_uri="/tmp/aereo_extract_test",
        search=None,
        extract=ExtractConfig(
            read=TestReader(),
            reproject=TestReprojector(),
            write=TestWriter(),
        ),
    )
    return ExtractionTask(
        assets=cast(GeoDataFrame[AssetSchema], df),
        job=job,
        patches=[patch],
        task_context={"job_id": "test-job", "chunk_id": 0},
    )


def test_handle_event_direct_payload(tmp_path: Any) -> None:
    """Direct mode runs a serialized task and writes results locally."""
    task = _make_task()
    payload = TaskSerializer().serialize_to_bytes(task)

    event = {
        "mode": "direct",
        "task": base64.b64encode(payload).decode("ascii"),
        "output_prefix": f"file://{tmp_path}/results/0/",
        "job_id": "test-job",
        "chunk_id": 0,
    }

    response = handle_event(event)

    assert response["statusCode"] == 200
    assert "manifest_uri" in response
    assert response["manifest_uri"].startswith(f"file://{tmp_path}/results/0/")


def test_handle_event_missing_output_prefix():
    """Missing output_prefix returns a 400 error."""
    response = handle_event({"mode": "direct", "task": "abc"})
    assert response["statusCode"] == 400
    assert "output_prefix" in response["error"]


def test_handle_event_staged_payload(tmp_path: Any):
    """Staged mode downloads a task from S3 and runs it."""
    task = _make_task()

    fake_s3 = _FakeS3Client()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = fake_s3

    # Stage the task in fake S3
    serializer = TaskSerializer()

    with tempfile.TemporaryDirectory() as tmpdir:
        serializer.serialize(task, Path(tmpdir))
        for file in Path(tmpdir).iterdir():
            fake_s3.upload_file(
                str(file), "aer-tasks", f"aereo-tasks/job/0/{file.name}"
            )

    event = {
        "mode": "staged",
        "task_uri": "s3://aer-tasks/aereo-tasks/job/0/",
        "output_prefix": f"file://{tmp_path}/results/0/",
        "job_id": "test-job",
        "chunk_id": 0,
    }

    with patch.dict("sys.modules", {"boto3": mock_boto3}):
        response = handle_event(event)

    assert response["statusCode"] == 200
    assert "manifest_uri" in response


def test_handle_lambda_is_handle_event():
    """handle_lambda delegates to handle_event."""
    event = {"output_prefix": "file:///tmp/out/"}
    response = handle_lambda(event, None)
    assert response["statusCode"] == 400


class _FakeS3Client:
    """In-memory S3 client for unit tests."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        data = self.objects[(bucket, key)]
        Path(filename).write_bytes(data)

    def get_paginator(self, name: str) -> "_FakePaginator":
        return _FakePaginator(self.objects, bucket="aer-tasks")


class _FakePaginator:
    def __init__(self, objects: dict[tuple[str, str], bytes], bucket: str) -> None:
        self.objects = objects
        self.bucket = bucket

    def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
        prefix = kwargs.get("Prefix", "")
        keys = [
            {"Key": key}
            for (bucket, key), _ in self.objects.items()
            if bucket == self.bucket and key.startswith(prefix)
        ]
        return [{"Contents": keys}]
