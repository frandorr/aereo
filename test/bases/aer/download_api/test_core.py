"""Tests for the smart download orchestrator (download_api base)."""

from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from aer.download_api import download


def make_test_gdf():
    from shapely.geometry import Polygon

    test_geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    df = pd.DataFrame(
        {
            "product_name": ["VNP"],
            "granule_id": ["G1"],
            "start_time": [pd.Timestamp("2024-01-01")],
            "end_time": [pd.Timestamp("2024-01-01")],
            "s3_url": ["s3://something/"],
            "https_url": ["https://example.com/a.hdf"],
            "size_mb": [1.0],
            "cell_row": ["10U"],
            "cell_col": ["20R"],
            "cell_dist": [100],
            "cell_epsg": ["EPSG:32615"],
            "cell_bounds": [test_geom],
            "channel_name": ["I1"],
            "cell_overlap_mode": ["contains"],
        }
    )
    return gpd.GeoDataFrame(df, geometry=[Point(0, 0)])


class TestDownloadSmartOrchestrator:
    @patch("aer.download_api.core.shutil.which")
    @patch("aer.download_api.core.download_aria2")
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

    @patch("aer.download_api.core.shutil.which")
    @patch("aer.download_api.core.download_raw")
    @patch("aer.download_api.core.logger.warning")
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
