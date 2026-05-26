"""Tests for CloudTaskStaging backend."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from aereo.backends.staging import CloudTaskStaging, _parse_s3_uri
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_artifacts() -> GeoDataFrame[ArtifactSchema]:
    """Return a minimal ArtifactSchema GeoDataFrame."""
    df = gpd.GeoDataFrame(
        {
            "grid_cell": ["A"],
            "grid_dist": [100],
            "cell_geometry": [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
            "cell_utm_crs": ["EPSG:32630"],
            "cell_utm_footprint": [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
            "id": ["art-1"],
            "source_ids": ["src-1"],
            "start_time": [pd.NaT],
            "end_time": [pd.NaT],
            "uri": ["s3://bucket/art.tif"],
            "geometry": [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
            "collection": ["test"],
        },
        crs="EPSG:4326",
    )
    # Register additional geometry columns so GeoParquet round-trips correctly.
    df = df.set_geometry("cell_geometry", crs="EPSG:4326")  # type: ignore[reportAttributeAccessIssue]
    df = df.set_geometry("cell_utm_footprint", crs="EPSG:4326")  # type: ignore[reportAttributeAccessIssue]
    return cast(GeoDataFrame[ArtifactSchema], df)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_parse_s3_uri():
    assert _parse_s3_uri("s3://my-bucket/path/to/key") == ("my-bucket", "path/to/key")
    assert _parse_s3_uri("s3://my-bucket/") == ("my-bucket", "")
    with pytest.raises(ValueError, match="Invalid S3 URI"):
        _parse_s3_uri("http://example.com")


def test_gcs_provider_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="GCS support coming soon"):
        CloudTaskStaging(bucket="test-bucket", provider="gcs")

    with pytest.raises(ValueError, match="Unsupported provider"):
        CloudTaskStaging(bucket="test-bucket", provider="azure")


def test_cloud_task_staging_stage():
    mock_s3 = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_s3

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        staging = CloudTaskStaging(
            bucket="test-bucket", provider="s3", endpoint_url="http://localhost:4566"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir)
            (src / "task_assets.parquet").write_text("fake")
            (src / "task_meta.json").write_text("{}")
            uri = staging.stage(src, "job-1", 0)

    assert uri == "s3://test-bucket/aereo-tasks/job-1/0/"
    assert mock_s3.upload_file.call_count == 2


class _FakeS3Client:
    """In-memory S3 client for testing load_artifacts / upload_artifacts."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        data = self.objects[(bucket, key)]
        Path(filename).write_bytes(data)


def test_cloud_task_staging_upload_and_load_artifacts():
    artifacts = _make_artifacts()
    fake_s3 = _FakeS3Client()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = fake_s3

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        staging = CloudTaskStaging(bucket="test-bucket", provider="s3")
        manifest = staging.upload_artifacts(
            artifacts, "s3://test-bucket/results/job/0/"
        )

    assert manifest["manifest_uri"] == "s3://test-bucket/results/job/0/manifest.json"

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        staging = CloudTaskStaging(bucket="test-bucket", provider="s3")
        loaded = staging.load_artifacts(manifest["manifest_uri"])

    assert len(loaded) == 1
    assert loaded["uri"].iloc[0] == "s3://bucket/art.tif"


def test_cloud_task_staging_load_artifacts_missing_key():
    fake_s3 = _FakeS3Client()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = fake_s3

    # Upload manifest without artifacts
    manifest = {"artifacts_uri": "s3://test-bucket/results/job/0/artifacts.parquet"}
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "manifest.json"
        p.write_text(json.dumps(manifest))
        fake_s3.upload_file(str(p), "test-bucket", "results/job/0/manifest.json")

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        staging = CloudTaskStaging(bucket="test-bucket", provider="s3")
        with pytest.raises(KeyError):
            staging.load_artifacts("s3://test-bucket/results/job/0/manifest.json")


def test_load_artifacts_cleans_up_temp_on_exception():
    """Simulate a download failure and verify no temp directories leak."""
    fake_s3 = _FakeS3Client()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = fake_s3

    # Upload a valid manifest
    manifest = {"artifacts_uri": "s3://test-bucket/results/job/0/artifacts.parquet"}
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "manifest.json"
        p.write_text(json.dumps(manifest))
        fake_s3.upload_file(str(p), "test-bucket", "results/job/0/manifest.json")

    # Track TemporaryDirectory instances to verify cleanup
    created_dirs: list[str] = []
    original_temporary_directory = tempfile.TemporaryDirectory

    class TrackingTemporaryDirectory(original_temporary_directory):
        def __enter__(self):
            path = super().__enter__()
            created_dirs.append(path)
            return path

        def __exit__(self, exc, value, tb):
            result = super().__exit__(exc, value, tb)
            # Only remove if it still exists (cleanup succeeded)
            if self.name in created_dirs:
                created_dirs.remove(self.name)
            return result

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        staging = CloudTaskStaging(bucket="test-bucket", provider="s3")
        with patch.object(tempfile, "TemporaryDirectory", TrackingTemporaryDirectory):
            with pytest.raises(KeyError):
                staging.load_artifacts("s3://test-bucket/results/job/0/manifest.json")

    assert not created_dirs, f"Leaked temporary directories: {created_dirs}"


def test_upload_artifacts_cleans_up_temp_on_exception():
    """Simulate an upload failure and verify no temp directories leak."""
    fake_s3 = _FakeS3Client()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = fake_s3

    # Make upload_file raise after the first call so the parquet upload succeeds
    # but the manifest upload fails.
    call_count = 0

    def counting_upload(filename: str, bucket: str, key: str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise RuntimeError("S3 upload failed")
        fake_s3.upload_file(filename, bucket, key)

    fake_s3.upload_file = counting_upload  # type: ignore[method-assign]

    created_dirs: list[str] = []
    original_temporary_directory = tempfile.TemporaryDirectory

    class TrackingTemporaryDirectory(original_temporary_directory):
        def __enter__(self):
            path = super().__enter__()
            created_dirs.append(path)
            return path

        def __exit__(self, exc, value, tb):
            result = super().__exit__(exc, value, tb)
            if self.name in created_dirs:
                created_dirs.remove(self.name)
            return result

    artifacts = _make_artifacts()

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        staging = CloudTaskStaging(bucket="test-bucket", provider="s3")
        with patch.object(tempfile, "TemporaryDirectory", TrackingTemporaryDirectory):
            with pytest.raises(RuntimeError, match="S3 upload failed"):
                staging.upload_artifacts(artifacts, "s3://test-bucket/results/job/0/")

    assert not created_dirs, f"Leaked temporary directories: {created_dirs}"
