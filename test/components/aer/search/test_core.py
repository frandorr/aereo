import pytest
from unittest.mock import patch, MagicMock
from aer.search import search_earthaccess
from aer.temporal import TimeRange
from aer.spectral import VNP02IMG, MODIS_02QKM
from datetime import datetime


def test_search_earthaccess_empty():
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )
    with patch("aer.search.core.earthaccess.search_data") as mock_search:
        mock_search.return_value = []
        df = search_earthaccess(products=[VNP02IMG], time_range=time_range)
        assert df.empty
        assert "product_name" in df.columns
        mock_search.assert_called_once()
        kwargs = mock_search.call_args.kwargs
        assert kwargs["short_name"] == [VNP02IMG.name]
        assert kwargs["temporal"] == ("2023-01-01 00:00:00", "2023-01-01 01:00:00")


def test_search_earthaccess_results():
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )
    with patch("aer.search.core.earthaccess.search_data") as mock_search:
        granule = MagicMock()
        granule.get.side_effect = lambda k, d=None: {
            "meta": {"native-id": "123", "concept-id": "C123"},
            "umm": {
                "CollectionReference": {"ShortName": VNP02IMG.name},
                "TemporalExtent": {
                    "RangeDateTime": {
                        "BeginningDateTime": "2023-01-01T00:05:00Z",
                        "EndingDateTime": "2023-01-01T00:10:00Z",
                    }
                },
            },
        }.get(k, d)
        granule.data_links.side_effect = lambda access="direct": (
            ["s3://bucket/test.nc"]
            if access == "direct"
            else ["https://bucket/test.nc"]
        )
        granule.size.return_value = 15.5

        mock_search.return_value = [granule]

        df = search_earthaccess(products=[VNP02IMG], time_range=time_range)
        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["product_name"] == VNP02IMG.name
        assert df.iloc[0]["s3_url"] == "s3://bucket/test.nc"
        assert df.iloc[0]["https_url"] == "https://bucket/test.nc"
        assert df.iloc[0]["size_mb"] == 15.5


@pytest.mark.slow
def test_search_earthaccess_real_vnp02img():
    # A known timeframe where VIIRS data should exist globally.
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 2, 0)
    )
    df = search_earthaccess(products=[VNP02IMG], time_range=time_range, count=10)

    assert not df.empty, (
        f"Expected non-empty results for {VNP02IMG.name} over {time_range}"
    )
    assert "product_name" in df.columns
    assert "s3_url" in df.columns
    assert df.iloc[0]["product_name"] == VNP02IMG.name


@pytest.mark.slow
def test_search_earthaccess_real_modis():
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 2, 0)
    )
    df = search_earthaccess(products=[MODIS_02QKM], time_range=time_range, count=10)

    assert not df.empty, (
        f"Expected non-empty results for {MODIS_02QKM.name} over {time_range}"
    )
    assert "product_name" in df.columns
    assert "s3_url" in df.columns
    assert df.iloc[0]["product_name"] == MODIS_02QKM.name


@pytest.mark.slow
def test_search_earthaccess_real_multiple():
    from aer.spectral import VNP03IMG

    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 1, 0)
    )
    df = search_earthaccess(
        products=[VNP02IMG, VNP03IMG], time_range=time_range, count=10
    )

    assert not df.empty, (
        f"Expected non-empty results for multiple products over {time_range}"
    )
    assert "product_name" in df.columns
    pnames = set(df["product_name"].unique())
    assert VNP02IMG.name in pnames
    assert VNP03IMG.name in pnames


@pytest.mark.slow
def test_search_earthaccess_real_multiple_constellations():
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 1, 0)
    )
    # Query across VIIRS (VNP02IMG) and MODIS (MODIS_02QKM)
    df = search_earthaccess(
        products=[VNP02IMG, MODIS_02QKM], time_range=time_range, count=10
    )

    assert not df.empty, (
        f"Expected non-empty results for multiple constellations over {time_range}"
    )
    assert "product_name" in df.columns
    pnames = set(df["product_name"].unique())
    assert VNP02IMG.name in pnames, f"Expected to find {VNP02IMG.name} in results"
    assert MODIS_02QKM.name in pnames, f"Expected to find {MODIS_02QKM.name} in results"
