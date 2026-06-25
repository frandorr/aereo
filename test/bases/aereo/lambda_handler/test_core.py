from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pandas as pd
from aereo.lambda_handler.core import handler
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


def test_handler_missing_task_uri():
    event = {"output_prefix": "s3://bucket/results/0/"}
    context: Any = MagicMock()
    result = handler(event, context)
    assert result["statusCode"] == 400
    assert "task_uri" in result["error"]


def test_handler_missing_output_prefix():
    event = {"task_uri": "s3://bucket/tasks/0/task_meta.json"}
    context: Any = MagicMock()
    result = handler(event, context)
    assert result["statusCode"] == 400
    assert "output_prefix" in result["error"]


@patch("aereo.lambda_handler.core._serializer")
@patch("aereo.lambda_handler.core.run_task")
@patch("aereo.lambda_handler.core._CloudTaskStaging")
def test_handler_success(
    mock_staging_class: MagicMock,
    mock_run_task: MagicMock,
    mock_serializer: MagicMock,
):
    import sys

    mock_s3 = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_s3

    mock_staging = MagicMock()
    mock_staging.upload_artifacts.return_value = {
        "manifest_uri": "s3://bucket/results/0/manifest.json"
    }
    mock_staging_class.return_value = mock_staging

    event = {
        "task_uri": "s3://bucket/tasks/0/",
        "output_prefix": "s3://bucket/results/0/",
        "job_id": "job-123",
        "chunk_id": 5,
    }
    context: Any = MagicMock()

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        result = handler(event, context)

    assert result["statusCode"] == 200
    assert result["manifest_uri"] == "s3://bucket/results/0/manifest.json"
    assert result["job_id"] == "job-123"
    assert result["chunk_id"] == 5

    mock_boto3.client.assert_called_once_with("s3", endpoint_url=None)
    mock_serializer.deserialize.assert_called_once()
    mock_run_task.assert_called_once()
    mock_staging_class.assert_called_once_with(bucket="bucket", endpoint_url=None)
    mock_staging.upload_artifacts.assert_called_once()


def _make_artifact_with_local_file(tmp_path: Path) -> GeoDataFrame[ArtifactSchema]:
    """Return an ArtifactSchema GeoDataFrame pointing at a real local file."""
    local_file = tmp_path / "test.tif"
    local_file.write_bytes(b"geotiff-bytes")
    df = gpd.GeoDataFrame(
        {
            "grid_cell": ["0U_0R"],
            "grid_dist": [1000],
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
            "uri": [str(local_file)],
            "geometry": gpd.GeoSeries(
                [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])], crs="EPSG:4326"
            ),
            "collection": ["test"],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )
    return GeoDataFrame[ArtifactSchema](df)


@patch("aereo.lambda_handler.core._serializer")
@patch("aereo.lambda_handler.core.run_task")
@patch("aereo.lambda_handler.core._CloudTaskStaging")
def test_handler_uploads_geotiffs_and_updates_uris(
    mock_staging_class: MagicMock,
    mock_run_task: MagicMock,
    mock_serializer: MagicMock,
    tmp_path: Path,
):
    """The handler uploads local GeoTIFF files and replaces URIs with S3 URIs."""
    import sys

    artifacts = _make_artifact_with_local_file(tmp_path)
    mock_run_task.return_value = artifacts

    uploaded_keys: list[tuple[str, str, str]] = []

    class _FakeS3:
        def get_paginator(self, name: str) -> "_FakePaginator":
            return _FakePaginator()

        def upload_file(self, filename: str, bucket: str, key: str) -> None:
            uploaded_keys.append((filename, bucket, key))

    class _FakePaginator:
        def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
            return []

    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = _FakeS3()

    captured_artifacts: list[GeoDataFrame[ArtifactSchema]] = []

    mock_staging = MagicMock()
    mock_staging.upload_artifacts.side_effect = lambda artifacts, prefix: (
        captured_artifacts.append(artifacts),
        {"manifest_uri": "s3://bucket/results/0/manifest.json"},
    )[1]
    mock_staging_class.return_value = mock_staging

    event = {
        "task_uri": "s3://bucket/tasks/0/",
        "output_prefix": "s3://bucket/results/0/",
        "job_id": "job-123",
        "chunk_id": 0,
    }
    context: Any = MagicMock()

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        result = handler(event, context)

    assert result["statusCode"] == 200
    assert len(uploaded_keys) == 1
    assert uploaded_keys[0][1] == "bucket"
    assert uploaded_keys[0][2] == "results/0/test.tif"

    assert len(captured_artifacts) == 1
    uploaded_artifacts = captured_artifacts[0]
    assert uploaded_artifacts["uri"].iloc[0] == "s3://bucket/results/0/test.tif"
