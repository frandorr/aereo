"""Tests for remote execution backends."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import urllib.error
from http.client import HTTPMessage
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from aereo.backends.lambda_backend import LambdaBackend, RetryableLambdaError
from aereo.interfaces import AereoPlugin
from aereo.interfaces.core import ExtractionTask, GridConfig, PatchConfig, ExtractConfig
from aereo.pipeline import ExtractionJob
from aereo.schemas.core import ArtifactSchema, AssetSchema
from aereo.storage import FileSystemStorage
from pandera.typing.geopandas import GeoDataFrame
from aereo.builtins.read import ReadODCSTAC
from aereo.builtins.reproject import ReprojectODC
from aereo.builtins.write import WriteGeoTIFF


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
    patch_config = PatchConfig(resolution=10.0)
    extract = ExtractConfig(
        read=ReadODCSTAC(),
        reproject=ReprojectODC(),
        write=WriteGeoTIFF(),
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


def _make_artifacts() -> GeoDataFrame[ArtifactSchema]:
    """Return a non-empty ArtifactSchema GeoDataFrame that can round-trip parquet."""
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
    with tempfile.TemporaryDirectory() as tmpdir:
        parquet_path = Path(tmpdir) / "artifacts.parquet"
        artifacts.to_parquet(parquet_path)
        s3.upload_file(str(parquet_path), bucket, f"{prefix}artifacts.parquet")

        manifest = {"artifacts_uri": f"s3://{bucket}/{prefix}artifacts.parquet"}
        manifest_path = Path(tmpdir) / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        s3.upload_file(str(manifest_path), bucket, f"{prefix}manifest.json")


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


def test_lambda_backend_lambda_url_does_not_require_boto3():
    """LambdaBackend accepts lambda_url without boto3 installed."""
    with patch.dict(sys.modules, {"boto3": None}):
        backend = LambdaBackend(
            function_name="ignored",
            staging=None,
            lambda_url="http://localhost:9000/2015-03-31/functions/function/invocations",
        )
    assert backend._lambda_client is None


def test_lambda_backend_lambda_url_posts_payload(tmp_path: Path):
    """LambdaBackend POSTs JSON payload to lambda_url and parses the response."""
    prefix = f"file://{tmp_path}/results/job-http/3/"
    manifest = FileSystemStorage().upload_artifacts(_make_artifacts(), prefix)

    task = _make_task(
        task_context={"job_id": "job-http", "chunk_id": 3},
    )

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {"manifest_uri": manifest["manifest_uri"]}
    ).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch.dict(sys.modules, {"boto3": None}):
        backend = LambdaBackend(
            function_name="ignored",
            staging=None,
            lambda_url="http://localhost:9000/2015-03-31/functions/function/invocations",
        )
        with patch(
            "urllib.request.urlopen", return_value=mock_response
        ) as mock_urlopen:
            results = list(backend.run_tasks([task]))

    assert len(results) == 1
    mock_urlopen.assert_called_once()
    request = mock_urlopen.call_args.args[0]
    assert (
        request.full_url
        == "http://localhost:9000/2015-03-31/functions/function/invocations"
    )
    assert request.get_method() == "POST"
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["job_id"] == "job-http"
    assert payload["chunk_id"] == 3
    assert payload["mode"] == "direct"
    assert "task" in payload


def test_lambda_backend_lambda_url_http_error_raises_runtime():
    """HTTP errors from lambda_url are surfaced as RuntimeError."""
    task = _make_task(task_context={"job_id": "job-http", "chunk_id": 0})

    error_body = b'{"error": "boom"}'
    error_fp = MagicMock()
    error_fp.read.return_value = error_body
    headers = HTTPMessage()
    http_error = urllib.error.HTTPError(
        url="http://localhost/invocations",
        code=500,
        msg="Internal Server Error",
        hdrs=headers,
        fp=error_fp,
    )

    with patch.dict(sys.modules, {"boto3": None}):
        backend = LambdaBackend(
            function_name="ignored",
            staging=None,
            lambda_url="http://localhost/invocations",
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            with pytest.raises(RuntimeError, match="Lambda HTTP invocation failed"):
                list(backend.run_tasks([task]))


def test_lambda_backend_direct_mode_posts_base64_task(tmp_path: Path):
    """staging=None sends the task as a base64 zip payload."""
    prefix = f"file://{tmp_path}/out/"
    manifest = FileSystemStorage().upload_artifacts(_make_artifacts(), prefix)

    task = _make_task(task_context={"job_id": "direct", "chunk_id": 0})

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {"manifest_uri": manifest["manifest_uri"]}
    ).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch.dict(sys.modules, {"boto3": None}):
        backend = LambdaBackend(
            function_name="ignored",
            staging=None,
            lambda_url="http://localhost:8080/extract",
        )
        with patch(
            "urllib.request.urlopen", return_value=mock_response
        ) as mock_urlopen:
            results = list(backend.run_tasks([task]))

    assert len(results) == 1
    payload = json.loads(mock_urlopen.call_args.args[0].data.decode("utf-8"))
    assert payload["mode"] == "direct"
    assert "task" in payload
    assert payload["output_prefix"].startswith("file://")


def test_lambda_backend_auto_uses_staging_for_large_task():
    """staging='auto' falls back to S3 when the task exceeds the threshold."""
    task = _make_task(task_context={"job_id": "auto", "chunk_id": 0})

    fake_s3 = _FakeS3Client()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = fake_s3

    # Pre-populate the result manifest + artifacts that the "remote worker" returns.
    result_prefix = "results/auto/0/"
    _upload_result_to_fake_s3(fake_s3, "aer-tasks", result_prefix, _make_artifacts())

    mock_payload = MagicMock()
    mock_payload.read.return_value = json.dumps(
        {"manifest_uri": f"s3://aer-tasks/{result_prefix}manifest.json"}
    ).encode("utf-8")

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        backend = LambdaBackend(
            function_name="aer-extract",
            staging="auto",
            staging_bucket="aer-tasks",
            direct_payload_threshold_bytes=1,
        )
        mock_client: Any = backend._lambda_client
        mock_client.invoke.return_value = {
            "Payload": mock_payload,
            "StatusCode": 200,
        }
        results = list(backend.run_tasks([task]))

    assert len(results) == 1
    payload = json.loads(mock_client.invoke.call_args.kwargs["Payload"].decode("utf-8"))
    assert payload["mode"] == "staged"
    assert payload["task_uri"].startswith("s3://aer-tasks/aereo-tasks/auto/0/")


def test_lambda_backend_auto_direct_for_small_task(tmp_path: Path):
    """staging='auto' sends a direct payload when the task is small enough."""
    prefix = f"file://{tmp_path}/out/"
    manifest = FileSystemStorage().upload_artifacts(_make_artifacts(), prefix)

    task = _make_task(task_context={"job_id": "auto", "chunk_id": 0})

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {"manifest_uri": manifest["manifest_uri"]}
    ).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch.dict(sys.modules, {"boto3": None}):
        backend = LambdaBackend(
            function_name="ignored",
            staging="auto",
            lambda_url="http://localhost:8080/extract",
            direct_payload_threshold_bytes=100 * 1024 * 1024,
        )
        with patch(
            "urllib.request.urlopen", return_value=mock_response
        ) as mock_urlopen:
            results = list(backend.run_tasks([task]))

    assert len(results) == 1
    payload = json.loads(mock_urlopen.call_args.args[0].data.decode("utf-8"))
    assert payload["mode"] == "direct"


def test_lambda_backend_lambda_url_rejects_explicit_staging():
    """lambda_url with an explicit TaskStaging instance raises ValueError."""
    staging = _FakeStaging()
    with pytest.raises(ValueError, match="lambda_url requires direct payloads"):
        LambdaBackend(
            function_name="ignored",
            staging=staging,
            lambda_url="http://localhost/invocations",
        )
