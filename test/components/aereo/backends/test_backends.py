"""Tests for remote execution backends."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from aereo.backends.lambda_backend import LambdaBackend, RetryableLambdaError
from aereo.interfaces import AereoPlugin
from aereo.interfaces.core import ExtractionTask, GridConfig
from aereo.schemas.core import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    pipeline: list[AereoPlugin] | None = None,
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
    return ExtractionTask(
        assets=cast(GeoDataFrame[AssetSchema], df),
        pipeline=pipeline or [],
        uri="test-uri",
        grid_cells=[],
        grid_config=grid_config,
        task_context=task_context or {},
    )


class _FakeStaging:
    """Fake TaskStaging for unit tests."""

    bucket = "aer-test-bucket"

    def __init__(self) -> None:
        self.staged: list[tuple[Path, str, int]] = []
        self.artifacts_to_return: list[GeoDataFrame[ArtifactSchema]] = []
        self._call_idx = 0

    def stage(self, src_dir: Path, job_id: str, task_idx: int) -> str:
        self.staged.append((src_dir, job_id, task_idx))
        return f"s3://{self.bucket}/tasks/{job_id}/{task_idx}/"

    def load_artifacts(self, manifest_uri: str) -> GeoDataFrame[ArtifactSchema]:
        gdf = self.artifacts_to_return[self._call_idx]
        self._call_idx += 1
        return gdf

    def result_prefix(self, job_id: str, task_idx: int) -> str:
        return f"s3://{self.bucket}/results/{job_id}/{task_idx}/"

    def upload_artifacts(
        self,
        artifacts: GeoDataFrame[ArtifactSchema],
        output_prefix: str,
    ) -> dict[str, str]:
        return {"manifest_uri": f"{output_prefix}manifest.json"}


def _make_empty_artifacts() -> GeoDataFrame[ArtifactSchema]:
    return cast(GeoDataFrame, ArtifactSchema.empty())


# ---------------------------------------------------------------------------
# LambdaBackend tests
# ---------------------------------------------------------------------------


def test_lambda_backend_raises_without_boto3():
    """Instantiating LambdaBackend without boto3 installed raises ImportError."""
    staging = MagicMock()
    with patch.dict(sys.modules, {"boto3": None}):
        with pytest.raises(ImportError, match="boto3 is required"):
            LambdaBackend(
                function_name="test-fn",
                staging=staging,
            )


def test_lambda_backend_invokes_lambda_for_single_task():
    """LambdaBackend serializes, stages, invokes, and loads one task."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    staging = _FakeStaging()
    staging.artifacts_to_return = [_make_empty_artifacts()]

    task = _make_task(task_context={"job_id": "job-42", "chunk_id": 7})

    # Build a mock Lambda response
    mock_payload = MagicMock()
    mock_payload.read.return_value = json.dumps(
        {"manifest_uri": "s3://bucket/results/job-42/7/manifest.json"}
    ).encode("utf-8")
    mock_client.invoke.return_value = {
        "Payload": mock_payload,
        "StatusCode": 200,
    }

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
        )
        results = list(backend.run_tasks([task], runner=MagicMock()))

    assert len(results) == 1
    assert len(staging.staged) == 1
    _, job_id, task_idx = staging.staged[0]
    assert job_id == "job-42"
    assert task_idx == 7

    mock_client.invoke.assert_called_once()
    call_kwargs = mock_client.invoke.call_args.kwargs
    assert call_kwargs["FunctionName"] == "aer-extract"
    payload = json.loads(call_kwargs["Payload"].decode("utf-8"))
    assert payload["task_uri"] == "s3://aer-test-bucket/tasks/job-42/7/"
    assert payload["output_prefix"] == "s3://aer-test-bucket/results/job-42/7/"


def test_lambda_backend_invokes_lambda_for_multiple_tasks():
    """LambdaBackend dispatches each task as a separate Lambda invocation."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    staging = _FakeStaging()
    staging.artifacts_to_return = [
        _make_empty_artifacts(),
        _make_empty_artifacts(),
    ]

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
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
        )
        results = list(backend.run_tasks(tasks, runner=MagicMock()))

    assert len(results) == 2
    assert mock_client.invoke.call_count == 2


def test_lambda_backend_propagates_function_error():
    """If Lambda returns FunctionError, a RuntimeError is raised."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    staging = _FakeStaging()
    task = _make_task(task_context={"job_id": "job-1", "chunk_id": 0})

    mock_payload = MagicMock()
    mock_payload.read.return_value = b"Unhandled error"
    mock_client.invoke.return_value = {
        "Payload": mock_payload,
        "StatusCode": 200,
        "FunctionError": "Unhandled",
    }

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
        )
        with pytest.raises(RuntimeError, match="Lambda function .* returned error"):
            list(backend.run_tasks([task], runner=MagicMock()))


def test_lambda_backend_raises_on_missing_manifest_uri():
    """If the Lambda payload lacks manifest_uri, ValueError is raised."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    staging = _FakeStaging()
    task = _make_task(task_context={"job_id": "job-1", "chunk_id": 0})

    mock_payload = MagicMock()
    mock_payload.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")
    mock_client.invoke.return_value = {
        "Payload": mock_payload,
        "StatusCode": 200,
    }

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
        )
        with pytest.raises(ValueError, match="missing 'manifest_uri'"):
            list(backend.run_tasks([task], runner=MagicMock()))


def test_lambda_backend_uses_custom_serializer():
    """A custom TaskSerializer can be injected."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    custom_serializer = MagicMock()
    staging = _FakeStaging()
    staging.artifacts_to_return = [_make_empty_artifacts()]
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
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
            serializer=custom_serializer,
        )
        list(backend.run_tasks([task], runner=MagicMock()))

    custom_serializer.serialize.assert_called_once()


def test_lambda_backend_uses_endpoint_url():
    """The endpoint_url is passed through to boto3.client."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    staging = _FakeStaging()
    staging.artifacts_to_return = [_make_empty_artifacts()]
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
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
            endpoint_url="http://localhost:4566",
        )
        list(backend.run_tasks([task], runner=MagicMock()))

    call_args = mock_boto3.client.call_args
    assert call_args.kwargs["endpoint_url"] == "http://localhost:4566"


def test_lambda_backend_concurrent_invokes_with_thread_pool():
    """LambdaBackend dispatches multiple tasks concurrently using ThreadPoolExecutor."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    staging = _FakeStaging()
    staging.artifacts_to_return = [
        _make_empty_artifacts(),
        _make_empty_artifacts(),
        _make_empty_artifacts(),
    ]

    tasks = [
        _make_task(task_context={"job_id": "job-99", "chunk_id": 0}),
        _make_task(task_context={"job_id": "job-99", "chunk_id": 1}),
        _make_task(task_context={"job_id": "job-99", "chunk_id": 2}),
    ]

    invoke_timestamps: list[float] = []

    def _tracked_invoke(*args, **kwargs):
        invoke_timestamps.append(time.monotonic())
        payload = MagicMock()
        payload.read.return_value = json.dumps(
            {"manifest_uri": "s3://bucket/results/manifest.json"}
        ).encode("utf-8")
        return {"Payload": payload, "StatusCode": 200}

    mock_client.invoke.side_effect = _tracked_invoke

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
            max_concurrent_invokes=3,
        )
        results = list(backend.run_tasks(tasks, runner=MagicMock()))

    assert len(results) == 3
    assert mock_client.invoke.call_count == 3
    # Concurrent dispatch means timestamps should be very close
    if len(invoke_timestamps) >= 2:
        assert max(invoke_timestamps) - min(invoke_timestamps) < 1.0


def test_lambda_backend_respects_max_concurrent_invokes():
    """max_concurrent_invokes parameter is stored and used."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    staging = _FakeStaging()

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
            max_concurrent_invokes=5,
        )
        assert backend.max_concurrent_invokes == 5


def test_lambda_backend_boto3_config_with_timeout_and_retries():
    """boto3 client is created with Config containing read_timeout and retries."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_config_class = MagicMock()
    mock_botocore_config = MagicMock()
    mock_botocore_config.Config = mock_config_class

    staging = _FakeStaging()

    with patch.dict(
        sys.modules,
        {"boto3": mock_boto3, "botocore.config": mock_botocore_config},
    ):
        LambdaBackend(
            function_name="aer-extract",
            staging=staging,
            invoke_timeout=600,
        )

    mock_config_class.assert_called_once_with(
        read_timeout=600,
        retries={"max_attempts": 3, "mode": "adaptive"},
    )


def test_lambda_backend_retryable_error_raises_retryable_lambda_error():
    """Structured retryable errors from Lambda raise RetryableLambdaError."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    staging = _FakeStaging()
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
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
        )
        with pytest.raises(RetryableLambdaError, match="Connection timed out"):
            list(backend.run_tasks([task], runner=MagicMock()))


def test_lambda_backend_structured_error_not_retryable_raises_runtime_error():
    """Structured non-retryable errors from Lambda raise RuntimeError."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    staging = _FakeStaging()
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
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
        )
        with pytest.raises(RuntimeError, match="Lambda returned error"):
            list(backend.run_tasks([task], runner=MagicMock()))


def test_safe_truncate_redacts_credentials():
    """_safe_truncate redacts AWS credentials and presigned URLs."""
    from aereo.backends.lambda_backend import _safe_truncate

    text = (
        "Error accessing https://bucket.s3.amazonaws.com/key?X-Amz-Credential=abc123 "
        "with key AKIAIOSFODNN7EXAMPLE and more text"
    )
    result = _safe_truncate(text)
    assert "[REDACTED-PRESIGNED-URL]" in result
    assert "[REDACTED-AWS-KEY]" in result
    assert "abc123" not in result
    assert "AKIAIOSFODNN7EXAMPLE" not in result


def test_lambda_backend_run_tasks_with_no_runner():
    """LambdaBackend accepts runner=None (default) since it ignores the runner."""
    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    staging = _FakeStaging()
    staging.artifacts_to_return = [_make_empty_artifacts()]
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
        backend = LambdaBackend(
            function_name="aer-extract",
            staging=staging,
        )
        results = list(backend.run_tasks([task]))

    assert len(results) == 1


def test_safe_truncate_truncates_long_text():
    """_safe_truncate truncates text exceeding max_len."""
    from aereo.backends.lambda_backend import _safe_truncate

    text = "x" * 3000
    result = _safe_truncate(text, max_len=2048)
    assert len(result) < 3000
    assert "truncated" in result
