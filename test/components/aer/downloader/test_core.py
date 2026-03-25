"""Tests for the downloader domain model (registry, value objects, URI utilities)."""

from aer.downloader import (
    DownloadedResultSchema,
    DownloadStatus,
    s3_uri_to_https,
)


import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


class TestDownloadedResultSchema:
    def test_validates_schema(self):
        from shapely.geometry import Polygon

        test_geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        df = pd.DataFrame(
            {
                "unique_id": ["U1"],
                "product_id": ["VNP02IMG"],
                "granule_id": ["G1"],
                "start_time": [pd.Timestamp("2024-01-01T00:00:00")],
                "end_time": [pd.Timestamp("2024-01-01T00:05:00")],
                "s3_url": ["s3://bucket/data.nc"],
                "https_url": ["https://example.com/data.nc"],
                "size_mb": [10.5],
                "local_path": ["/tmp/data.nc"],
                "download_status": [DownloadStatus.COMPLETE.value],
                "name": ["10U_20R"],
                "row": ["10U"],
                "col": ["20R"],
                "row_idx": [0],
                "col_idx": [0],
                "utm_zone": ["31N"],
                "epsg": ["EPSG:32615"],
                "cell_bounds": [test_geom],
                "channel": ["I1"],
                "overlap_mode": ["contains"],
            }
        )
        gdf = gpd.GeoDataFrame(df, geometry=[Point(0, 0)])

        # Should pass validation
        validated = DownloadedResultSchema.validate(gdf)
        assert len(validated) == 1
        assert validated.iloc[0]["download_status"] == "complete"


# ---------------------------------------------------------------------------
# s3_uri_to_https
# ---------------------------------------------------------------------------


class TestS3UriToHttps:
    def test_passthrough_https(self):
        url = "https://example.com/data/file.hdf"
        assert s3_uri_to_https(url) == url

    def test_passthrough_http(self):
        url = "http://example.com/data/file.hdf"
        assert s3_uri_to_https(url) == url

    def test_s3_with_custom_endpoint(self):
        endpoints = {"prod-lads": "https://ladsweb.example.com/data"}
        result = s3_uri_to_https(
            "s3://prod-lads/MOD021KM/file.hdf", endpoint_map=endpoints
        )
        assert result == "https://ladsweb.example.com/data/MOD021KM/file.hdf"

    def test_s3_fallback_aws_virtual_hosted(self):
        result = s3_uri_to_https("s3://my-public-bucket/path/to/file.nc")
        assert result == "https://my-public-bucket.s3.amazonaws.com/path/to/file.nc"

    def test_s3_no_endpoints_provided(self):
        result = s3_uri_to_https("s3://bucket/key.hdf")
        assert result == "https://bucket.s3.amazonaws.com/key.hdf"

    def test_s3_url_encodes_special_chars(self):
        result = s3_uri_to_https("s3://bucket/path/file name (1).hdf")
        assert "file%20name%20%281%29.hdf" in result

    def test_s3_preserves_path_separators(self):
        result = s3_uri_to_https("s3://bucket/a/b/c/file.hdf")
        assert result == "https://bucket.s3.amazonaws.com/a/b/c/file.hdf"

    def test_custom_endpoint_strips_trailing_slash(self):
        endpoints = {"mybucket": "https://cdn.example.com/"}
        result = s3_uri_to_https("s3://mybucket/file.hdf", endpoint_map=endpoints)
        assert result == "https://cdn.example.com/file.hdf"
