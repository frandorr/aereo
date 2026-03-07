"""Tests for the aria2c-based download backend (parallel via input file)."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import pytest

from aer.downloader import DownloadStatus
from aer.downloader_aria2.core import (
    download_aria2,
    _resolve_filename,
    _ensure_aria2c,
    _write_input_file,
)


def make_test_gdf(urls):
    if not urls:
        df = pd.DataFrame(
            columns=[
                "product_name",
                "granule_id",
                "start_time",
                "end_time",
                "s3_url",
                "https_url",
                "size_mb",
                "geometry",
            ]
        )
        return gpd.GeoDataFrame(df, geometry="geometry")

    df = pd.DataFrame(
        {
            "product_name": ["VNP"] * len(urls),
            "granule_id": [f"G{i}" for i in range(len(urls))],
            "start_time": [pd.Timestamp("2024-01-01")] * len(urls),
            "end_time": [pd.Timestamp("2024-01-01")] * len(urls),
            "s3_url": ["s3://something/"] * len(urls),
            "https_url": urls,
            "size_mb": [1.0] * len(urls),
        }
    )
    return gpd.GeoDataFrame(df, geometry=[Point(0, 0)] * len(urls))


class TestResolveFilename:
    def test_derived_from_uri(self):
        assert _resolve_filename("https://x.com/data/file.hdf") == "file.hdf"

    def test_strips_query_params(self):
        assert _resolve_filename("https://x.com/data/file.hdf?token=abc") == "file.hdf"

    def test_fallback_download(self):
        assert _resolve_filename("https://x.com/") == "download"


class TestEnsureAria2c:
    @patch("aer.downloader_aria2.core.shutil.which", return_value="/usr/bin/aria2c")
    def test_found(self, mock_which):
        assert _ensure_aria2c() == "/usr/bin/aria2c"

    @patch("aer.downloader_aria2.core.shutil.which", return_value=None)
    def test_not_found(self, mock_which):
        with pytest.raises(FileNotFoundError, match="aria2c is not installed"):
            _ensure_aria2c()


class TestWriteInputFile:
    def test_basic_input_file(self, tmp_path):
        out = tmp_path / "input.txt"
        _write_input_file(
            ["https://example.com/file.hdf"], ["file.hdf"], Path("/data/out"), out
        )

        content = out.read_text()
        assert "https://example.com/file.hdf" in content
        assert "dir=/data/out" in content
        assert "out=file.hdf" in content

    def test_input_file_with_headers(self, tmp_path):
        out = tmp_path / "input.txt"
        _write_input_file(
            ["https://example.com/file.hdf"],
            ["file.hdf"],
            Path("/data/out"),
            out,
            headers={"Authorization": "Bearer tok123"},
        )

        content = out.read_text()
        assert "header=Authorization: Bearer tok123" in content


class TestDownloadAria2:
    def test_empty_requests(self):
        gdf = make_test_gdf([])
        results = download_aria2(gdf, "/tmp")
        assert len(results) == 0

    @patch("aer.downloader_aria2.core.shutil.which", return_value="/usr/bin/aria2c")
    @patch("aer.downloader_aria2.core.subprocess.run")
    def test_successful_parallel_download(self, mock_run, mock_which, tmp_path):
        dest = tmp_path / "output"
        dest.mkdir()

        (dest / "a.hdf").write_bytes(b"x" * 512)
        (dest / "b.hdf").write_bytes(b"y" * 256)

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        gdf = make_test_gdf(["https://example.com/a.hdf", "https://example.com/b.hdf"])
        results = download_aria2(gdf, str(dest))

        assert len(results) == 2
        assert results.iloc[0]["download_status"] == DownloadStatus.COMPLETE.value
        assert results.iloc[0]["local_path"] == str(dest / "a.hdf")
        assert results.iloc[1]["download_status"] == DownloadStatus.COMPLETE.value
        assert results.iloc[1]["local_path"] == str(dest / "b.hdf")

    @patch("aer.downloader_aria2.core.shutil.which", return_value="/usr/bin/aria2c")
    @patch("aer.downloader_aria2.core.subprocess.run")
    def test_partial_failure(self, mock_run, mock_which, tmp_path):
        dest = tmp_path / "output"
        dest.mkdir()

        (dest / "a.hdf").write_bytes(b"data")

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Some error"
        )

        gdf = make_test_gdf(["https://example.com/a.hdf", "https://example.com/b.hdf"])
        results = download_aria2(gdf, str(dest))

        assert len(results) == 2
        assert results.iloc[0]["download_status"] == DownloadStatus.COMPLETE.value
        assert results.iloc[1]["download_status"] == DownloadStatus.FAILED.value
