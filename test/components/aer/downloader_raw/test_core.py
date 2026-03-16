"""Tests for the raw Python based download backend."""

import io
import urllib.error
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from aer.downloader import DownloadStatus

from aer.downloader_raw.core import (
    download_raw,
    _resolve_filename,
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
                "overlapping_spatial_extent",
                "input_spatial_extent",
                "cell_overlap_mode",
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
            "overlapping_spatial_extent": [None] * len(urls),
            "input_spatial_extent": [None] * len(urls),
            "cell_overlap_mode": ["contains"] * len(urls),
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


class TestDownloadRaw:
    def test_empty_requests(self):
        gdf = make_test_gdf([])
        results = download_raw(gdf, "/tmp")
        assert len(results) == 0

    @patch("aer.downloader_raw.core.urllib.request.urlopen")
    def test_successful_parallel_download(self, mock_urlopen, tmp_path):
        dest = tmp_path / "output"
        dest.mkdir()

        def side_effect(req, timeout):
            return io.BytesIO(b"data" * 128)

        mock_urlopen.side_effect = side_effect

        gdf = make_test_gdf(["https://example.com/a.hdf", "https://example.com/b.hdf"])
        results = download_raw(gdf, str(dest))

        assert len(results) == 2
        assert results.iloc[0]["download_status"] == DownloadStatus.COMPLETE.value
        assert results.iloc[0]["local_path"] == str(dest / "a.hdf")
        assert results.iloc[1]["download_status"] == DownloadStatus.COMPLETE.value
        assert results.iloc[1]["local_path"] == str(dest / "b.hdf")

    @patch("aer.downloader_raw.core.urllib.request.urlopen")
    def test_partial_failure(self, mock_urlopen, tmp_path):
        dest = tmp_path / "output"
        dest.mkdir()

        def side_effect(req, timeout):
            if "a.hdf" in req.full_url:
                return io.BytesIO(b"data")
            else:
                raise urllib.error.URLError("Not found")

        mock_urlopen.side_effect = side_effect

        gdf = make_test_gdf(["https://example.com/a.hdf", "https://example.com/b.hdf"])
        results = download_raw(gdf, str(dest))

        assert len(results) == 2
        # a.hdf landed on disk → complete
        assert results.iloc[0]["download_status"] == DownloadStatus.COMPLETE.value
        # b.hdf is missing → failed
        assert results.iloc[1]["download_status"] == DownloadStatus.FAILED.value

    @patch("aer.downloader_raw.core.urllib.request.urlopen")
    def test_headers_passed(self, mock_urlopen, tmp_path):
        dest = tmp_path / "output"
        dest.mkdir()

        called_headers = {}

        def side_effect(req, timeout):
            called_headers.update(req.headers)
            return io.BytesIO(b"data")

        mock_urlopen.side_effect = side_effect

        gdf = make_test_gdf(["https://example.com/file.hdf"])
        download_raw(
            gdf, dest_dir=str(dest), headers={"Authorization": "Bearer tok123"}
        )

        # urllib Request capitalizes headers, depending on how they are added
        # By default it Capitalizes initial letters
        assert "Authorization" in called_headers
        assert called_headers["Authorization"] == "Bearer tok123"

    def test_rows_with_missing_https_url_are_skipped(self, tmp_path):
        """Rows with None in https_url should be marked as 'skipped'."""
        dest = tmp_path / "output"
        dest.mkdir()

        df = pd.DataFrame(
            {
                "product_name": ["VNP", "VNP"],
                "granule_id": ["G0", "G1"],
                "start_time": [pd.Timestamp("2024-01-01")] * 2,
                "end_time": [pd.Timestamp("2024-01-01")] * 2,
                "s3_url": ["s3://something/", "s3://something/"],
                "https_url": [None, None],
                "size_mb": [1.0, 1.0],
                "overlapping_spatial_extent": [None, None],
                "input_spatial_extent": [None, None],
                "cell_overlap_mode": ["contains", "contains"],
            }
        )
        gdf = gpd.GeoDataFrame(df, geometry=[Point(0, 0), Point(1, 1)])
        results = download_raw(gdf, str(dest))

        assert len(results) == 2
        assert (results["download_status"] == DownloadStatus.SKIPPED.value).all()
        assert results["local_path"].isna().all()
