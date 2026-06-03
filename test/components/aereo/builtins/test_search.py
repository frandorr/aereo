from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from aereo.builtins.search import SearchSTAC
from aereo.interfaces import AereoProfile
from shapely.geometry import Polygon


@pytest.fixture
def mock_pystac_item():
    mock_item = MagicMock()
    mock_item.id = "test-item-123"
    mock_item.collection_id = "test-collection"
    mock_item.geometry = {
        "type": "Polygon",
        "coordinates": [
            [[10.0, 45.0], [11.0, 45.0], [11.0, 46.0], [10.0, 46.0], [10.0, 45.0]]
        ],
    }
    mock_item.datetime = datetime(2023, 5, 12, 10, 10, 31, tzinfo=timezone.utc)
    mock_item.properties = {"datetime": "2023-05-12T10:10:31Z"}
    mock_item.to_dict.return_value = {"id": "test-item-123", "type": "Feature"}

    mock_asset_b04 = MagicMock()
    mock_asset_b04.href = "https://example.com/b04.tif"

    mock_asset_visual = MagicMock()
    mock_asset_visual.href = "https://example.com/visual.tif"

    mock_item.assets = {"B04": mock_asset_b04, "visual": mock_asset_visual}

    return mock_item


def test_search_stac_missing_api_url():
    provider = SearchSTAC()
    profile = AereoProfile(
        name="test",
        resolution=10,
        collections={"test-collection": []},
    )
    with pytest.raises(ValueError, match="stac_api_url must be provided"):
        provider.search(profiles=[profile], search_params={})


@patch("aereo.builtins.search.Client")
def test_search_stac_connection_error(mock_client):
    mock_client.open.side_effect = Exception("Connection timed out")
    provider = SearchSTAC()
    profile = AereoProfile(
        name="test",
        resolution=10,
        collections={"test-collection": []},
    )
    with pytest.raises(ValueError, match="Failed to connect to STAC API"):
        provider.search(
            profiles=[profile],
            search_params={"stac_api_url": "https://example.com/stac"},
        )


@patch("aereo.builtins.search.Client")
def test_search_stac_query_error(mock_client):
    mock_catalog = MagicMock()
    mock_client.open.return_value = mock_catalog
    mock_catalog.search.side_effect = Exception("Invalid query parameter")

    provider = SearchSTAC()
    profile = AereoProfile(
        name="test",
        resolution=10,
        collections={"test-collection": []},
    )
    with pytest.raises(ValueError, match="STAC search query failed"):
        provider.search(
            profiles=[profile],
            search_params={"stac_api_url": "https://example.com/stac"},
        )


@patch("aereo.builtins.search.Client")
def test_search_stac_empty_results(mock_client):
    mock_catalog = MagicMock()
    mock_client.open.return_value = mock_catalog
    mock_search_request = MagicMock()
    mock_search_request.items.return_value = []
    mock_catalog.search.return_value = mock_search_request

    provider = SearchSTAC()
    profile = AereoProfile(
        name="test",
        resolution=10,
        collections={"test-collection": []},
    )
    result = provider.search(
        profiles=[profile],
        search_params={"stac_api_url": "https://example.com/stac"},
    )
    assert result.empty
    assert "geometry" in result.columns


@patch("aereo.builtins.search.Client")
def test_search_stac_with_assets_filter(mock_client, mock_pystac_item):
    mock_catalog = MagicMock()
    mock_client.open.return_value = mock_catalog
    mock_search_request = MagicMock()
    mock_search_request.items.return_value = [mock_pystac_item]
    mock_catalog.search.return_value = mock_search_request

    provider = SearchSTAC()
    profile = AereoProfile(
        name="test",
        resolution=10,
        collections={"test-collection": []},
    )
    result = provider.search(
        profiles=[profile],
        search_params={
            "stac_api_url": "https://example.com/stac",
            "assets": ["B04"],
        },
    )

    assert not result.empty
    assert len(result) == 1
    assert result.iloc[0]["id"] == "test-item-123_B04"
    assert result.iloc[0]["channel_id"] == "B04"
    assert result.iloc[0]["href"] == "https://example.com/b04.tif"


@patch("aereo.builtins.search.Client")
def test_search_stac_with_channel_filter(mock_client, mock_pystac_item):
    mock_catalog = MagicMock()
    mock_client.open.return_value = mock_catalog
    mock_search_request = MagicMock()
    mock_search_request.items.return_value = [mock_pystac_item]
    mock_catalog.search.return_value = mock_search_request

    provider = SearchSTAC()
    profile = AereoProfile(
        name="test",
        resolution=10,
        collections={"test-collection": ["visual"]},
    )
    result = provider.search(
        profiles=[profile],
        search_params={"stac_api_url": "https://example.com/stac"},
    )

    assert not result.empty
    assert len(result) == 1
    assert result.iloc[0]["id"] == "test-item-123_visual"
    assert result.iloc[0]["channel_id"] == "visual"
    assert result.iloc[0]["href"] == "https://example.com/visual.tif"


@patch("aereo.builtins.search.Client")
def test_search_stac_default_first_asset(mock_client, mock_pystac_item):
    mock_catalog = MagicMock()
    mock_client.open.return_value = mock_catalog
    mock_search_request = MagicMock()
    mock_search_request.items.return_value = [mock_pystac_item]
    mock_catalog.search.return_value = mock_search_request

    provider = SearchSTAC()
    profile = AereoProfile(
        name="test",
        resolution=10,
        collections={"test-collection": []},
    )
    result = provider.search(
        profiles=[profile],
        search_params={"stac_api_url": "https://example.com/stac"},
    )

    assert not result.empty
    assert len(result) == 1
    # B04 is the first key in the item.assets dict
    assert result.iloc[0]["id"] == "test-item-123_B04"
    assert result.iloc[0]["channel_id"] == "B04"


@patch("aereo.builtins.search.Client")
def test_search_stac_headers_passing(mock_client, mock_pystac_item):
    mock_catalog = MagicMock()
    mock_client.open.return_value = mock_catalog
    mock_search_request = MagicMock()
    mock_search_request.items.return_value = [mock_pystac_item]
    mock_catalog.search.return_value = mock_search_request

    provider = SearchSTAC()
    profile = AereoProfile(
        name="test",
        resolution=10,
        collections={"test-collection": []},
    )
    provider.search(
        profiles=[profile],
        search_params={
            "stac_api_url": "https://example.com/stac",
            "headers": {"Authorization": "Bearer token", "X-Custom": 123},
        },
    )

    mock_client.open.assert_called_once_with(
        "https://example.com/stac",
        headers={"Authorization": "Bearer token", "X-Custom": "123"},
    )


@patch("aereo.builtins.search.Client")
def test_search_stac_params_forwarding_and_datetime(mock_client, mock_pystac_item):
    mock_catalog = MagicMock()
    mock_client.open.return_value = mock_catalog
    mock_search_request = MagicMock()
    mock_search_request.items.return_value = [mock_pystac_item]
    mock_catalog.search.return_value = mock_search_request

    provider = SearchSTAC()
    profile1 = AereoProfile(
        name="test1",
        resolution=10,
        collections={"collection-a": []},
    )
    profile2 = AereoProfile(
        name="test2",
        resolution=10,
        collections={"collection-b": []},
    )

    start_dt = datetime(2023, 5, 12, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(2023, 5, 13, 0, 0, 0, tzinfo=timezone.utc)
    polygon = Polygon(
        [(10.0, 45.0), (11.0, 45.0), (11.0, 46.0), (10.0, 46.0), (10.0, 45.0)]
    )

    provider.search(
        profiles=[profile1, profile2],
        intersects=polygon,
        start_datetime=start_dt,
        end_datetime=end_dt,
        search_params={
            "stac_api_url": "https://example.com/stac",
            "limit": 50,
            "query": {"eo:cloud_cover": {"lt": 10}},
        },
    )

    mock_catalog.search.assert_called_once()
    search_kwargs = mock_catalog.search.call_args[1]

    assert set(search_kwargs["collections"]) == {"collection-a", "collection-b"}
    assert search_kwargs["datetime"] == "2023-05-12T00:00:00Z/2023-05-13T00:00:00Z"
    assert search_kwargs["intersects"] == polygon.__geo_interface__
    assert search_kwargs["limit"] == 50
    assert search_kwargs["query"] == {"eo:cloud_cover": {"lt": 10}}


@patch("aereo.builtins.search.Client")
def test_search_stac_partial_datetimes(mock_client, mock_pystac_item):
    mock_catalog = MagicMock()
    mock_client.open.return_value = mock_catalog
    mock_search_request = MagicMock()
    mock_search_request.items.return_value = [mock_pystac_item]
    mock_catalog.search.return_value = mock_search_request

    provider = SearchSTAC()
    profile = AereoProfile(
        name="test",
        resolution=10,
        collections={"test-collection": []},
    )
    start_dt = datetime(2023, 5, 12, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(2023, 5, 13, 0, 0, 0, tzinfo=timezone.utc)

    # Start date only
    provider.search(
        profiles=[profile],
        start_datetime=start_dt,
        search_params={"stac_api_url": "https://example.com/stac"},
    )
    assert mock_catalog.search.call_args[1]["datetime"] == "2023-05-12T00:00:00Z/.."

    mock_catalog.reset_mock()

    # End date only
    provider.search(
        profiles=[profile],
        end_datetime=end_dt,
        search_params={"stac_api_url": "https://example.com/stac"},
    )
    assert mock_catalog.search.call_args[1]["datetime"] == "../2023-05-13T00:00:00Z"
