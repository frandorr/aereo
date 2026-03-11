"""Tests for the smart downloader."""

from unittest.mock import patch

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

from aer.downloader import download


def make_test_gdf():
    df = pd.DataFrame(
        {
            "product_name": ["VNP"],
            "granule_id": ["G1"],
            "start_time": [pd.Timestamp("2024-01-01")],
            "end_time": [pd.Timestamp("2024-01-01")],
            "s3_url": ["s3://something/"],
            "https_url": ["https://example.com/a.hdf"],
            "size_mb": [1.0],
        }
    )
    return gpd.GeoDataFrame(df, geometry=[Point(0, 0)])


class TestDownloadSmartOrchestrator:
    @patch("aer.downloader.core.shutil.which")
    @patch("aer.downloader_aria2.download_aria2")
    def test_uses_aria2_if_available(self, mock_download_aria2, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/aria2c"
        gdf = make_test_gdf()

        download(gdf, dest_dir=str(tmp_path), max_concurrent=2)

        mock_which.assert_called_once_with("aria2c")
        mock_download_aria2.assert_called_once_with(
            gdf,
            str(tmp_path),
            max_concurrent=2,
            timeout=600,
            verbose=False,
            headers=None,
            options=None,
            extra_args=None,
        )

    @patch("aer.downloader.core.shutil.which")
    @patch("aer.downloader_raw.download_raw")
    @patch("aer.downloader.core.logger.warning")
    def test_uses_raw_if_aria2_missing(
        self, mock_warning, mock_download_raw, mock_which, tmp_path
    ):
        mock_which.return_value = None
        gdf = make_test_gdf()

        download(gdf, dest_dir=str(tmp_path), max_concurrent=2)

        mock_which.assert_called_once_with("aria2c")
        mock_warning.assert_called_once()
        mock_download_raw.assert_called_once_with(
            gdf,
            str(tmp_path),
            max_concurrent=2,
            timeout=600,
            verbose=False,
            headers=None,
            options=None,
            extra_args=None,
        )
