"""Tests for the generic download pipeline module."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import geopandas as gpd
from hamilton import driver
from shapely.geometry import Point

from aereo.pipeline import download as download_module


def test_supported_collections_is_wildcard() -> None:
    """The download module supports any collection."""
    assert download_module.supported_collections == ("*",)


def test_local_dir_from_task_uri() -> None:
    """local_dir derives a path from the task URI for local URIs."""
    task = MagicMock()
    task.uri = "/tmp/aereo-output"
    result = download_module.local_dir(task)
    assert result == Path("/tmp/aereo-output/downloads")
    assert result.exists()


def test_local_dir_fallback_for_remote_uri() -> None:
    """local_dir falls back to /tmp/aereo-downloads for remote URIs."""
    task = MagicMock()
    task.uri = "s3://bucket/prefix"
    result = download_module.local_dir(task)
    assert result == Path("/tmp/aereo-downloads")


def test_local_dir_fallback_for_empty_uri() -> None:
    """local_dir falls back when task.uri is empty."""
    task = MagicMock()
    task.uri = ""
    result = download_module.local_dir(task)
    assert result == Path("/tmp/aereo-downloads")


@patch("aereo.pipeline.download.download_assets_safely")
def test_download_assets_empty(mock_download: Any) -> None:
    """download_assets returns an empty dict when task.assets is empty."""
    task = MagicMock()
    task.assets = gpd.GeoDataFrame()
    result = download_module.download_assets(
        task=task,
        local_dir=Path("/tmp/test"),
    )
    assert result == {}
    mock_download.assert_not_called()


@patch("aereo.pipeline.download.download_assets_safely")
def test_download_assets_downloads_files(mock_download: Any, tmp_path: Path) -> None:
    """download_assets maps asset ids to local paths and calls download_assets_safely."""
    task = MagicMock()
    task.assets = gpd.GeoDataFrame(
        {
            "id": ["asset-1", "asset-2"],
            "href": ["http://example.com/file1.nc", "http://example.com/file2.zip"],
        },
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:4326",
    )
    task.profile = MagicMock()
    task.profile.downloader = None

    local_dir = tmp_path / "downloads"
    result = download_module.download_assets(
        task=task,
        local_dir=local_dir,
        max_workers=2,
        store_options={"region": "us-east-1"},
    )

    assert "asset-1" in result
    assert "asset-2" in result
    assert result["asset-1"].name == "asset-1_file1.nc"
    assert result["asset-2"].name == "asset-2_file2.zip"

    mock_download.assert_called_once()
    call_args = mock_download.call_args.kwargs
    assert call_args["hrefs"] == [
        "http://example.com/file1.nc",
        "http://example.com/file2.zip",
    ]
    assert call_args["downloader"] is None
    assert call_args["max_workers"] == 2
    assert call_args["store_options"] == {"region": "us-east-1"}


@patch("aereo.pipeline.download.download_assets_safely")
def test_download_assets_uses_profile_downloader(
    mock_download: Any, tmp_path: Path
) -> None:
    """download_assets resolves downloader from task.profile.downloader."""
    custom_downloader = MagicMock()
    task = MagicMock()
    task.assets = gpd.GeoDataFrame(
        {
            "id": ["asset-1"],
            "href": ["http://example.com/file.nc"],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:4326",
    )
    task.profile = MagicMock()
    task.profile.downloader = custom_downloader

    local_dir = tmp_path / "downloads"
    download_module.download_assets(
        task=task,
        local_dir=local_dir,
    )

    mock_download.assert_called_once()
    assert mock_download.call_args.kwargs["downloader"] is custom_downloader


def test_extracted_assets_passthrough_non_archives() -> None:
    """extracted_assets forwards non-zip files unchanged."""
    paths = {
        "asset-1": Path("/tmp/downloads/asset-1_file.nc"),
        "asset-2": Path("/tmp/downloads/asset-2_file.tif"),
    }
    result = download_module.extracted_assets(paths)
    assert result == paths


def test_extracted_assets_extracts_zip(tmp_path: Path) -> None:
    """extracted_assets extracts .zip files to sibling directories."""
    zip_path = tmp_path / "asset-1_data.zip"
    extract_dir = tmp_path / "asset-1_data"
    marker = extract_dir.with_suffix(".extracted")

    # Create a dummy zip file
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("dummy.txt", "hello")

    paths = {"asset-1": zip_path}
    result = download_module.extracted_assets(paths)

    assert result["asset-1"] == extract_dir
    assert extract_dir.exists()
    assert (extract_dir / "dummy.txt").exists()
    assert marker.exists()


def test_extracted_assets_skips_extraction_when_disabled() -> None:
    """extracted_assets returns inputs unchanged when extract_archives is False."""
    paths = {"asset-1": Path("/tmp/downloads/asset-1_data.zip")}
    result = download_module.extracted_assets(paths, extract_archives=False)
    assert result == paths


def test_download_pipeline_runs() -> None:
    """download.py can be built into a Hamilton driver and executes extracted_assets."""
    dr = driver.Builder().with_modules(download_module).build()
    task = MagicMock()
    task.uri = "/tmp/aereo-test"
    task.assets = gpd.GeoDataFrame(
        {
            "id": ["asset-1"],
            "href": ["http://example.com/file.nc"],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:4326",
    )
    task.profile = MagicMock()
    task.profile.downloader = None

    with patch("aereo.pipeline.download.download_assets_safely") as mock_dl:
        mock_dl.return_value = None
        result = dr.execute(
            ["extracted_assets"],
            inputs={"task": task},
        )
        assert "extracted_assets" in result
        assert isinstance(result["extracted_assets"], dict)
