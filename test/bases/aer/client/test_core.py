from unittest.mock import MagicMock
import pytest
import pandas as pd
from shapely.geometry import Point

from aer.registry.core import AerRegistry
from aer.client.core import AerClient, FailureMode, normalize_geometry
from aer.schemas.core import AssetSchema, ArtifactSchema
from aer.interfaces.core import ExtractionTask


def test_normalize_geometry_dict_to_shapely():
    geom_dict = {"type": "Point", "coordinates": [10.0, 20.0]}
    shapely_geom = normalize_geometry(geom_dict)
    assert isinstance(shapely_geom, Point)
    assert shapely_geom.x == 10.0
    assert shapely_geom.y == 20.0


def test_normalize_geometry_invalid():
    with pytest.raises(ValueError, match="Invalid geometry format"):
        normalize_geometry("Not a dict or geometry")


def test_client_search_success(monkeypatch):
    mock_registry = MagicMock(spec=AerRegistry)

    # Setup mock registry to return valid dummy data
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    # It must return a GeoDataFrame that passes AssetSchema validation
    monkeypatch.setattr("aer.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df.loc[1] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "MODIS"
    mock_searcher.search.return_value = valid_df

    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)

    # 1. Search
    search_results = client.search(
        collections=["MODIS"], intersects={"type": "Point", "coordinates": [0, 0]}
    )

    # Validations
    assert len(search_results) == 2
    mock_registry.find_searchers_for.assert_called_with("MODIS")
    mock_registry.get_searcher.assert_called_with("dummy_searcher")
    mock_searcher.search.assert_called_once()
    assert isinstance(search_results, pd.DataFrame)


def test_client_search_normalizes_collections(monkeypatch):
    """Verify that collection names are mapped to plugin's declared format before being passed to plugins."""
    mock_registry = MagicMock(spec=AerRegistry)

    # Setup mock registry to return valid dummy data for lowercase collection name
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    # Setup mock mapping to return plugin's declared format (lowercase in this case)
    mock_registry.get_collection_mapping_for_searcher.return_value = ["goes-abi1"]

    mock_searcher = MagicMock()
    monkeypatch.setattr("aer.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "GOES-Abi1"
    mock_searcher.search.return_value = valid_df

    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)

    # Search with uppercase collection name - should be mapped to plugin's format
    client.search(
        collections=["GOES-Abi1"],
        start_datetime=None,
        end_datetime=None,
    )

    # Verify mapping was called
    mock_registry.get_collection_mapping_for_searcher.assert_called_once_with(
        "dummy_searcher", ["GOES-Abi1"]
    )

    # The plugin should receive mapped collection name
    call_args = mock_searcher.search.call_args
    assert call_args is not None
    passed_collections = list(call_args.kwargs.get("collections", []))
    assert "goes-abi1" in passed_collections, (
        f"Expected mapped collection, got: {passed_collections}"
    )


def test_client_search_all_fail_strict():
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    mock_searcher.search.side_effect = Exception("API Down")
    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)

    with pytest.raises(RuntimeError, match="All search plugins failed strictly"):
        client.search(collections=["MODIS"], failure_mode=FailureMode.STRICT)


def test_client_search_all_fail_best_effort():
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    mock_searcher.search.side_effect = Exception("API Down")
    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)

    # Will not raise, returns an empty geometry
    search_results = client.search(
        collections=["MODIS"], failure_mode=FailureMode.BEST_EFFORT
    )
    assert len(search_results) == 0


def test_client_run_pipeline_e2e(monkeypatch):
    mock_registry = MagicMock(spec=AerRegistry)

    # -- Search Setup --
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]
    mock_searcher = MagicMock()
    monkeypatch.setattr("aer.schemas.core.AssetSchema.validate", lambda x: x)
    monkeypatch.setattr("aer.schemas.core.ArtifactSchema.validate", lambda x: x)

    valid_search_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_search_df.loc[0] = {
        col: "test" for col in AssetSchema.to_schema().columns.keys()
    }
    valid_search_df["geometry"] = Point(0, 0)
    valid_search_df["collection"] = "MODIS"
    mock_searcher.search.return_value = valid_search_df

    mock_registry.get_searcher.return_value = mock_searcher

    # -- Extractor Setup --
    mock_registry.find_extractors_for.return_value = ["dummy_extractor"]
    mock_extractor = MagicMock()
    from typing import cast
    from pandera.typing.geopandas import GeoDataFrame

    from aer.interfaces.core import ExtractionProfile

    task = ExtractionTask(
        assets=cast(GeoDataFrame, valid_search_df),
        profile=ExtractionProfile(name="test", resolution=10),
        uri="test-uri",
        grid_cells=[],
    )
    mock_extractor.prepare_for_extraction.return_value = [task]
    # It must extract and return an ArtifactSchema
    valid_artifact_df = pd.DataFrame(
        columns=list(ArtifactSchema.to_schema().columns.keys())
    )
    valid_artifact_df.loc[0] = {
        col: "test" for col in ArtifactSchema.to_schema().columns.keys()
    }
    valid_artifact_df["geometry"] = Point(0, 0)
    mock_extractor.extract_batches.return_value = valid_artifact_df

    mock_registry.get_extractor.return_value = mock_extractor

    client = AerClient(registry=mock_registry)

    # Run the big convenient wrapper
    final_df = client.run_pipeline(collections=["MODIS"], resolution=10)

    assert len(final_df) == 1
    mock_searcher.search.assert_called_once()
    mock_extractor.prepare_for_extraction.assert_called_once()
    mock_extractor.extract_batches.assert_called_once()


# ---------------------------------------------------------------------------
# _resolve_params – case-insensitive parameter resolution
# ---------------------------------------------------------------------------


def _make_client_with_collections(*collections: str) -> AerClient:
    """Return an AerClient whose registry reports the given known collections."""
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.list_supported_collections.return_value = list(collections)
    return AerClient(registry=mock_registry)


def test_resolve_params_none_returns_empty():
    client = _make_client_with_collections("sentinel-2-l2a")
    assert client._resolve_params(None, "sentinel-2-l2a") == {}


def test_resolve_params_global_params_pass_through():
    """Non-collection keys are passed to every plugin unchanged."""
    client = _make_client_with_collections("sentinel-2-l2a")
    result = client._resolve_params({"limit": 100, "cloud_cover": 20}, "sentinel-2-l2a")
    assert result == {"limit": 100, "cloud_cover": 20}


def test_resolve_params_override_exact_case():
    """Exact-case collection key is merged and the collection key itself is stripped."""
    client = _make_client_with_collections("sentinel-2-l2a")
    params = {
        "limit": 10,
        "sentinel-2-l2a": {"channels": ["B02", "B03"]},
    }
    result = client._resolve_params(params, "sentinel-2-l2a")
    assert result == {"limit": 10, "channels": ["B02", "B03"]}


def test_resolve_params_override_mixed_case_key():
    """User writes 'Sentinel-2-L2A' as the key but the collection is 'sentinel-2-l2a'."""
    client = _make_client_with_collections("sentinel-2-l2a")
    params = {
        "limit": 5,
        "Sentinel-2-L2A": {"channels": ["B04"]},
    }
    result = client._resolve_params(params, "sentinel-2-l2a")
    assert result == {"limit": 5, "channels": ["B04"]}


def test_resolve_params_override_upper_case_collection_arg():
    """Collection arg is upper-cased but the key in params is lowercase."""
    client = _make_client_with_collections("sentinel-2-l2a")
    params = {
        "sentinel-2-l2a": {"channels": ["B08"]},
    }
    result = client._resolve_params(params, "SENTINEL-2-L2A")
    assert result == {"channels": ["B08"]}


def test_resolve_params_strips_other_collection_keys():
    """Keys for *other* collections are stripped; only the target's override is merged."""
    client = _make_client_with_collections("sentinel-2-l2a", "ABI-L1b-RadF")
    params = {
        "limit": 20,
        "sentinel-2-l2a": {"channels": ["B02"]},
        "ABI-L1b-RadF": {"satellite": "GOES-19"},
    }
    # Resolving for sentinel-2-l2a should NOT include the GOES block
    result = client._resolve_params(params, "sentinel-2-l2a")
    assert result == {"limit": 20, "channels": ["B02"]}
    assert "ABI-L1b-RadF" not in result
    assert "satellite" not in result


def test_resolve_params_strips_other_collection_keys_case_insensitive():
    """Case variants of other collection names are also stripped."""
    client = _make_client_with_collections("sentinel-2-l2a", "ABI-L1b-RadF")
    params = {
        "SENTINEL-2-L2A": {"channels": ["B03"]},
        "abi-l1b-radf": {"satellite": "GOES-16"},
    }
    result = client._resolve_params(params, "Sentinel-2-L2A")
    assert result == {"channels": ["B03"]}
    assert "abi-l1b-radf" not in result


# ---------------------------------------------------------------------------
# _normalize_hints – case-insensitive plugin_hints helper
# ---------------------------------------------------------------------------


def test_normalize_hints_lowercases_keys():
    result = AerClient._normalize_hints(
        {"Sentinel-2-L2A": "my_plugin", "ABI-L1b-RadF": "goes_plugin"}
    )
    assert result == {"sentinel-2-l2a": "my_plugin", "abi-l1b-radf": "goes_plugin"}


def test_normalize_hints_empty():
    assert AerClient._normalize_hints({}) == {}


def test_normalize_hints_inverted_format():
    """Inverted format: plugin -> [collections] should expand to collection -> plugin."""
    result = AerClient._normalize_hints({"extract_satpy": ["VJ202IMG", "VJ203IMG"]})
    assert result == {
        "vj202img": "extract_satpy",
        "vj203img": "extract_satpy",
    }


def test_normalize_hints_inverted_format_lowercases_collections():
    """Collection names in inverted format should be lower-cased."""
    result = AerClient._normalize_hints(
        {"MyPlugin": ["Sentinel-2-L2A", "ABI-L1b-RadF"]}
    )
    assert result == {
        "sentinel-2-l2a": "MyPlugin",
        "abi-l1b-radf": "MyPlugin",
    }


def test_normalize_hints_mixed_formats():
    """Legacy and inverted formats can coexist (though not recommended)."""
    result = AerClient._normalize_hints(
        {
            "MODIS": "legacy_plugin",  # legacy
            "extract_satpy": ["VJ202IMG", "VJ203IMG"],  # inverted
        }
    )
    assert result == {
        "modis": "legacy_plugin",
        "vj202img": "extract_satpy",
        "vj203img": "extract_satpy",
    }


def test_search_plugin_hint_inverted_format(monkeypatch):
    """Inverted plugin_hints should resolve correctly for search."""
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.find_searchers_for.return_value = []  # No auto-discovery
    mock_registry.get_collection_mapping_for_searcher.return_value = ["modis"]
    mock_registry.list_supported_collections.return_value = ["modis"]

    mock_searcher = MagicMock()
    monkeypatch.setattr("aer.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "modis"
    mock_searcher.search.return_value = valid_df
    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)
    client.search(
        collections=["modis"],
        plugin_hints={"preferred_searcher": ["modis"]},  # inverted
    )
    mock_registry.get_searcher.assert_called_with("preferred_searcher")


def test_search_plugin_hint_case_insensitive(monkeypatch):
    """plugin_hints key 'MODIS' should match collection 'modis' and vice-versa."""
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.find_searchers_for.return_value = []  # No auto-discovery result
    mock_registry.get_collection_mapping_for_searcher.return_value = ["modis"]
    mock_registry.list_supported_collections.return_value = ["modis"]

    mock_searcher = MagicMock()
    monkeypatch.setattr("aer.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "modis"
    mock_searcher.search.return_value = valid_df
    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)

    # User passes upper-case hint key, lower-case collection
    client.search(
        collections=["modis"],
        plugin_hints={"MODIS": "preferred_searcher"},  # upper-case key
    )

    mock_registry.get_searcher.assert_called_with("preferred_searcher")
