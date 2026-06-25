"""Tests for the LambdaExecutor remote executor."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from aereo.executors import LambdaExecutor, RetryableLambdaError
from aereo.interfaces.core import ExtractionTask, ExtractConfig, GridConfig, PatchConfig
from aereo.pipeline import ExtractionJob
from aereo.schemas.core import ArtifactSchema, AssetSchema
from aereo.builtins.read import read_odc_stac
from aereo.builtins.reproject import reproject_odc
from aereo.builtins.write import write_geotiff
from pandera.typing.geopandas import GeoDataFrame


@pytest.fixture(autouse=True)
def _mock_botocore():
    """Automatically mock botocore and botocore.config in sys.modules."""
    mock_botocore = MagicMock()
    mock_config = MagicMock()
    with patch.dict(
        sys.modules, {"botocore": mock_botocore, "botocore.config": mock_config}
    ):
        yield


def _make_task(
    pipeline: list[Any] | None = None,
    task_context: dict[str, Any] | None = None,
) -> ExtractionTask:
    """Return a minimal ExtractionTask for testing."""
    from datetime import datetime

    df = gpd.GeoDataFrame(
        {
            "id": ["asset_1"],
            "collection": ["GOES"],
            "start_time": [datetime(2023, 1, 1, 12, 0)],
            "end_time": [datetime(2023, 1, 1, 12, 30)],
            "href": ["s3://bucket/key.tif"],
        },
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
        crs="EPSG:4326",
    )

    grid_config = GridConfig(target_grid_dist=50_000)
    patch_config = PatchConfig(resolution=10.0)
    extract = ExtractConfig(
        read=read_odc_stac,
        reproject=reproject_odc,
        write=write_geotiff,
    )
    job = ExtractionJob(
        grid_config=grid_config,
        patch_config=patch_config,
        output_uri="test-uri",
        extract=extract,
    )
    return ExtractionTask(
        assets=cast(GeoDataFrame[AssetSchema], df),
        job=job,
        patches=[],
        task_context=task_context or {},
    )


def _make_empty_artifacts() -> GeoDataFrame[ArtifactSchema]:
    return cast(GeoDataFrame, ArtifactSchema.empty())


def _make_artifacts() -> GeoDataFrame[ArtifactSchema]:
    """Return a non-empty ArtifactSchema GeoDataFrame."""
    df = gpd.GeoDataFrame(
        {
            "grid_cell": ["A"],
            "grid_dist": [100],
            "cell_geometry": gpd.GeoSeries(
                [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])], crs="EPSG:4326"
            ),
            "cell_utm_crs": ["EPSG:32630"],
            "cell_utm_footprint": gpd.GeoSeries(
                [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])], crs="EPSG:4326"
            ),
            "id": ["art-1"],
            "source_ids": ["src-1"],
            "start_time": [pd.Timestamp("2024-01-01T00:00:00Z")],
            "end_time": [pd.Timestamp("2024-01-01T00:00:00Z")],
            "uri": ["file:///tmp/art.tif"],
            "geometry": gpd.GeoSeries(
                [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])], crs="EPSG:4326"
            ),
            "collection": ["test"],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )
    return cast(GeoDataFrame[ArtifactSchema], df)


class _FakeS3Client:
    """In-memory S3 client for unit tests."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.invoke = MagicMock(
            return_value={"Payload": MagicMock(), "StatusCode": 200}
        )

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        data = self.objects[(bucket, key)]
        Path(filename).write_bytes(data)


def _upload_result_to_fake_s3(
    s3: _FakeS3Client,
    bucket: str,
    prefix: str,
    artifacts: GeoDataFrame[ArtifactSchema],
) -> None:
    """Upload artifacts and manifest to the in-memory fake S3 client."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        parquet_path = Path(tmpdir) / "artifacts.parquet"
        artifacts.to_parquet(parquet_path)
        s3.upload_file(str(parquet_path), bucket, f"{prefix}artifacts.parquet")

        manifest = {"artifacts_uri": f"s3://{bucket}/{prefix}artifacts.parquet"}
        manifest_path = Path(tmpdir) / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        s3.upload_file(str(manifest_path), bucket, f"{prefix}manifest.json")


def test_lambda_executor_raises_without_boto3():
    """Instantiating LambdaExecutor without boto3 installed raises ImportError."""
    with patch.dict(sys.modules, {"boto3": None}):
        with pytest.raises(ImportError, match="boto3 is required"):
            LambdaExecutor(
                function_name="test-fn",
                staging_bucket="test-bucket",
            )


def test_lambda_executor_invokes_lambda_for_single_task():
    """LambdaExecutor serializes, stages, invokes, and loads one task."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    task = _make_task(task_context={"job_id": "job-42", "chunk_id": 7})

    mock_payload = MagicMock()
    mock_payload.read.return_value = json.dumps(
        {"manifest_uri": "s3://bucket/results/job-42/7/manifest.json"}
    ).encode("utf-8")
    mock_client.invoke.return_value = {
        "Payload": mock_payload,
        "StatusCode": 200,
    }

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
        )
        with patch.object(
            executor, "_load_manifest", return_value=_make_empty_artifacts()
        ):
            artifacts = executor([task])

    assert isinstance(artifacts, gpd.GeoDataFrame)
    mock_client.invoke.assert_called_once()
    call_kwargs = mock_client.invoke.call_args.kwargs
    assert call_kwargs["FunctionName"] == "aer-extract"
    payload = json.loads(call_kwargs["Payload"].decode("utf-8"))
    assert payload["task_uri"].startswith("s3://aer-tasks/aereo-tasks/job-42/7/")
    assert payload["output_prefix"] == "s3://aer-tasks/results/job-42/7/"


def test_lambda_executor_invokes_lambda_for_multiple_tasks():
    """LambdaExecutor dispatches each task as a separate Lambda invocation."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    tasks = [
        _make_task(task_context={"job_id": "job-99", "chunk_id": 0}),
        _make_task(task_context={"job_id": "job-99", "chunk_id": 1}),
    ]

    def _make_response(manifest_uri: str):
        payload = MagicMock()
        payload.read.return_value = json.dumps({"manifest_uri": manifest_uri}).encode(
            "utf-8"
        )
        return {"Payload": payload, "StatusCode": 200}

    mock_client.invoke.side_effect = [
        _make_response("s3://bucket/results/job-99/0/manifest.json"),
        _make_response("s3://bucket/results/job-99/1/manifest.json"),
    ]

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
        )
        with patch.object(
            executor, "_load_manifest", return_value=_make_empty_artifacts()
        ):
            artifacts = executor(tasks)

    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert mock_client.invoke.call_count == 2


def test_lambda_executor_propagates_function_error():
    """If Lambda returns FunctionError, a RuntimeError is raised."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    task = _make_task(task_context={"job_id": "job-1", "chunk_id": 0})

    mock_payload = MagicMock()
    mock_payload.read.return_value = b"Unhandled error"
    mock_client.invoke.return_value = {
        "Payload": mock_payload,
        "StatusCode": 200,
        "FunctionError": "Unhandled",
    }

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
        )
        with pytest.raises(RuntimeError, match="Lambda function .* returned error"):
            executor([task])


def test_lambda_executor_raises_on_missing_manifest_uri():
    """If the Lambda payload lacks manifest_uri, ValueError is raised."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    task = _make_task(task_context={"job_id": "job-1", "chunk_id": 0})

    mock_payload = MagicMock()
    mock_payload.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")
    mock_client.invoke.return_value = {
        "Payload": mock_payload,
        "StatusCode": 200,
    }

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
        )
        with pytest.raises(ValueError, match="missing 'manifest_uri'"):
            executor([task])


def test_lambda_executor_uses_endpoint_url():
    """The endpoint_url is passed through to boto3.client."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    task = _make_task(task_context={"job_id": "job-1", "chunk_id": 0})

    mock_payload = MagicMock()
    mock_payload.read.return_value = json.dumps(
        {"manifest_uri": "s3://bucket/m.json"}
    ).encode("utf-8")
    mock_client.invoke.return_value = {
        "Payload": mock_payload,
        "StatusCode": 200,
    }

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
            endpoint_url="http://localhost:4566",
        )
        with patch.object(
            executor, "_load_manifest", return_value=_make_empty_artifacts()
        ):
            executor([task])

    call_args = mock_boto3.client.call_args
    assert call_args.kwargs["endpoint_url"] == "http://localhost:4566"


def test_lambda_executor_respects_max_concurrent_invokes():
    """max_concurrent_invokes parameter is stored and used."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
            max_concurrent_invokes=5,
        )
        assert executor.max_concurrent_invokes == 5


def test_lambda_executor_boto3_config_with_timeout_and_retries():
    """boto3 client is created with Config containing read_timeout and retries."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_config_class = MagicMock()
    mock_botocore_config = MagicMock()
    mock_botocore_config.Config = mock_config_class

    with patch.dict(
        sys.modules,
        {"boto3": mock_boto3, "botocore.config": mock_botocore_config},
    ):
        LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
            invoke_timeout=600,
        )

    mock_config_class.assert_called_once_with(
        read_timeout=600,
        retries={"max_attempts": 3, "mode": "adaptive"},
    )


def test_lambda_executor_retryable_error_raises_retryable_lambda_error():
    """Structured retryable errors from Lambda raise RetryableLambdaError."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    task = _make_task(task_context={"job_id": "job-1", "chunk_id": 0})

    mock_payload = MagicMock()
    mock_payload.read.return_value = json.dumps(
        {
            "statusCode": 500,
            "error": "Connection timed out",
            "retryable": True,
        }
    ).encode("utf-8")
    mock_client.invoke.return_value = {
        "Payload": mock_payload,
        "StatusCode": 200,
    }

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
        )
        with pytest.raises(RetryableLambdaError, match="Connection timed out"):
            executor([task])


def test_lambda_executor_structured_error_not_retryable_raises_runtime_error():
    """Structured non-retryable errors from Lambda raise RuntimeError."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    task = _make_task(task_context={"job_id": "job-1", "chunk_id": 0})

    mock_payload = MagicMock()
    mock_payload.read.return_value = json.dumps(
        {
            "statusCode": 400,
            "error": "Invalid task parameters",
            "retryable": False,
        }
    ).encode("utf-8")
    mock_client.invoke.return_value = {
        "Payload": mock_payload,
        "StatusCode": 200,
    }

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
        )
        with pytest.raises(RuntimeError, match="Lambda returned error"):
            executor([task])


def test_lambda_executor_stages_to_s3():
    """LambdaExecutor stages tasks to S3 and invokes Lambda."""
    task = _make_task(task_context={"job_id": "stage", "chunk_id": 0})

    fake_s3 = _FakeS3Client()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = fake_s3

    result_prefix = "results/stage/0/"
    _upload_result_to_fake_s3(fake_s3, "aer-tasks", result_prefix, _make_artifacts())

    mock_payload = MagicMock()
    mock_payload.read.return_value = json.dumps(
        {"manifest_uri": f"s3://aer-tasks/{result_prefix}manifest.json"}
    ).encode("utf-8")

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
        )
        mock_client: Any = executor._lambda_client
        mock_client.invoke.return_value = {
            "Payload": mock_payload,
            "StatusCode": 200,
        }
        with patch.object(executor, "_load_manifest", return_value=_make_artifacts()):
            artifacts = executor([task])

    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) == 1
    payload = json.loads(mock_client.invoke.call_args.kwargs["Payload"].decode("utf-8"))
    assert payload["mode"] == "staged"
    assert payload["task_uri"].startswith("s3://aer-tasks/aereo-tasks/stage/0/")


def test_lambda_executor_best_effort_skips_failed_tasks():
    """Best-effort mode returns successful tasks and skips failures."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    tasks = [
        _make_task(task_context={"job_id": "be", "chunk_id": 0}),
        _make_task(task_context={"job_id": "be", "chunk_id": 1}),
    ]

    def _side_effect(*args, **kwargs):
        payload = json.loads(kwargs["Payload"].decode("utf-8"))
        chunk_id = payload["chunk_id"]
        response_payload = MagicMock()
        if chunk_id == 0:
            response_payload.read.return_value = json.dumps(
                {"statusCode": 500, "error": "boom", "retryable": False}
            ).encode("utf-8")
        else:
            response_payload.read.return_value = json.dumps(
                {"manifest_uri": "s3://bucket/results/be/1/manifest.json"}
            ).encode("utf-8")
        return {"Payload": response_payload, "StatusCode": 200}

    mock_client.invoke.side_effect = _side_effect

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
            failure_mode="best_effort",
        )
        with patch.object(
            executor, "_load_manifest", return_value=_make_empty_artifacts()
        ):
            artifacts = executor(tasks)

    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert mock_client.invoke.call_count == 2


def test_lambda_executor_empty_tasks_returns_empty():
    """Calling LambdaExecutor with no tasks returns an empty GeoDataFrame."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        executor = LambdaExecutor(
            function_name="aer-extract",
            staging_bucket="aer-tasks",
        )
        artifacts = executor([])

    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) == 0
    mock_client.invoke.assert_not_called()
