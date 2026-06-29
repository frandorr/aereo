"""Tests for storage backends."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from aereo.schemas import ArtifactSchema
from aereo.storage import FileSystemStorage, S3Storage, storage_for_uri
from aereo.storage.s3 import _parse_s3_uri
from pandera.typing.geopandas import GeoDataFrame


def _make_artifacts() -> GeoDataFrame[ArtifactSchema]:
    """Return a minimal ArtifactSchema GeoDataFrame."""
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
            "start_time": [pd.NaT],
            "end_time": [pd.NaT],
            "uri": ["s3://bucket/art.tif"],
            "geometry": gpd.GeoSeries(
                [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])], crs="EPSG:4326"
            ),
            "collection": ["test"],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )
    return cast(GeoDataFrame[ArtifactSchema], df)


def test_storage_for_uri_s3():
    backend = storage_for_uri("s3://bucket/path/")
    assert isinstance(backend, S3Storage)


def test_storage_for_uri_file():
    backend = storage_for_uri("file:///tmp/aereo/out/")
    assert isinstance(backend, FileSystemStorage)


def test_storage_for_uri_unsupported():
    with pytest.raises(ValueError, match="Unsupported URI scheme"):
        storage_for_uri("gs://bucket/path/")


def test_filesystem_storage_roundtrip(tmp_path: Path):
    backend = FileSystemStorage()
    artifacts = _make_artifacts()
    prefix = f"file://{tmp_path}/results/job/0/"

    manifest = backend.upload_artifacts(artifacts, prefix)

    assert manifest["manifest_uri"] == f"{prefix}manifest.json"
    assert (tmp_path / "results" / "job" / "0" / "manifest.json").exists()
    assert (tmp_path / "results" / "job" / "0" / "artifacts.parquet").exists()

    loaded = backend.load_artifacts(manifest["manifest_uri"])
    assert len(loaded) == 1
    assert loaded["uri"].iloc[0] == "s3://bucket/art.tif"


def test_filesystem_storage_load_missing_key(tmp_path: Path):
    backend = FileSystemStorage()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({}))
    with pytest.raises(ValueError, match="Manifest missing"):
        backend.load_artifacts(f"file://{manifest_path}")


class _FakeS3Client:
    """In-memory S3 client for testing upload/download."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        data = self.objects[(bucket, key)]
        Path(filename).write_bytes(data)


def test_s3_storage_roundtrip():
    fake_s3 = _FakeS3Client()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = fake_s3

    artifacts = _make_artifacts()

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        backend = S3Storage(endpoint_url="http://localhost:4566")
        manifest = backend.upload_artifacts(
            artifacts, "s3://test-bucket/results/job/0/"
        )

    assert manifest["manifest_uri"] == "s3://test-bucket/results/job/0/manifest.json"
    assert mock_boto3.client.call_args[1]["endpoint_url"] == "http://localhost:4566"

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        loaded = backend.load_artifacts(manifest["manifest_uri"])

    assert len(loaded) == 1
    assert loaded["uri"].iloc[0] == "s3://bucket/art.tif"


def test_parse_s3_uri():
    assert _parse_s3_uri("s3://my-bucket/path/to/key") == ("my-bucket", "path/to/key")
    assert _parse_s3_uri("s3://my-bucket/") == ("my-bucket", "")
    with pytest.raises(ValueError, match="Invalid S3 URI"):
        _parse_s3_uri("http://example.com")
