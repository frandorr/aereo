import pytest
from datetime import datetime, timezone
from unittest.mock import patch
import geopandas as gpd
from aer.search import SearchQuery
from aer.search_goes_aws import search_goes_aws
from aer.temporal import TimeRange
from aer.spectral import ABI_L1B_RADF


@patch("s3fs.S3FileSystem")
def test_search_goes_aws_empty(mock_s3_cls):
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 12, 10, tzinfo=timezone.utc),
    )
    mock_fs = mock_s3_cls.return_value
    mock_fs.ls.return_value = []
    query = SearchQuery(products=[ABI_L1B_RADF], time_range=time_range)
    gdf = search_goes_aws(query)
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert gdf.empty
    assert "product_name" in gdf.columns


@patch("s3fs.S3FileSystem")
def test_search_goes_aws_results(mock_s3_cls):
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 12, 10, tzinfo=timezone.utc),
    )
    # Filename format: sYYYYJJJHHMMSS + optional digits
    filename = (
        "OR_ABI-L1b-RadF-M6C01_G16_s20240011200000_e20240011209590_c20240011210000.nc"
    )
    path = f"noaa-goes16/ABI-L1b-RadF/2024/001/12/{filename}"

    # Prefix our code will scan
    prefix = "noaa-goes16/ABI-L1b-RadF/2024/001/12/"

    mock_fs = mock_s3_cls.return_value
    mock_fs.ls.side_effect = lambda p, detail=False: (
        [{"name": path, "size": 1024 * 1024}] if p == prefix else []
    )

    query = SearchQuery(products=[ABI_L1B_RADF], time_range=time_range)
    gdf = search_goes_aws(query)

    assert not gdf.empty
    assert len(gdf) == 1
    assert gdf.iloc[0]["granule_id"] == filename
    assert gdf.iloc[0]["s3_url"] == f"s3://{path}"
    assert gdf.iloc[0]["size_mb"] == 1.0


@pytest.mark.integration
@pytest.mark.slow
def test_search_goes_aws_real():
    # Use a real satellite and time that we know has data
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 12, 1, tzinfo=timezone.utc),
    )
    query = SearchQuery(products=[ABI_L1B_RADF], time_range=time_range)
    gdf = search_goes_aws(query)

    assert not gdf.empty, "Expected to find GOES files on AWS for 2024-001 12:00"
    assert "s3_url" in gdf.columns
    assert gdf.iloc[0]["product_name"] == "ABI-L1b-RadF"
