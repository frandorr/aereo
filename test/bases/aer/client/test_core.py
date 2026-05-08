from typing import cast
from unittest.mock import MagicMock

import pytest
import pandas as pd
from shapely.geometry import Point

from aer.interfaces.core import AerProfile, ExtractionTask
from aer.registry.core import AerRegistry
from aer.client.core import AerClient, FailureMode, normalize_geometry
from aer.schemas.core import AssetSchema
from pandera.typing.geopandas import GeoDataFrame


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

    profile = AerProfile(name="modis", resolution=1000.0, collections=["MODIS"])

    # 1. Search
    search_results = client.search(
        profiles=[profile], intersects={"type": "Point", "coordinates": [0, 0]}
    )

    # Validations
    assert len(search_results) == 2
    mock_registry.find_searchers_for.assert_called_with("MODIS")
    mock_registry.get_searcher.assert_called_with("dummy_searcher")
    mock_searcher.search.assert_called_once()
    assert isinstance(search_results, pd.DataFrame)


def test_client_search_accepts_profiles(monkeypatch):
    """search() must pass profiles (not collections) to the plugin."""
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    monkeypatch.setattr("aer.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "MODIS"
    mock_searcher.search.return_value = valid_df
    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)
    profile = AerProfile(name="p1", resolution=10.0, collections=["MODIS"])
    client.search(profiles=[profile])

    call_kwargs = mock_searcher.search.call_args.kwargs
    assert "profiles" in call_kwargs
    assert call_kwargs["profiles"][0].name == "p1"


def test_client_search_all_fail_strict():
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    mock_searcher.search.side_effect = Exception("API Down")
    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)
    profile = AerProfile(name="modis", resolution=1000.0, collections=["MODIS"])

    with pytest.raises(RuntimeError, match="All search plugins failed strictly"):
        client.search(profiles=[profile], failure_mode=FailureMode.STRICT)


def test_client_search_all_fail_best_effort():
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    mock_searcher.search.side_effect = Exception("API Down")
    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)
    profile = AerProfile(name="modis", resolution=1000.0, collections=["MODIS"])

    # Will not raise, returns an empty geometry
    search_results = client.search(
        profiles=[profile], failure_mode=FailureMode.BEST_EFFORT
    )
    assert len(search_results) == 0


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
# _resolve_plugin_for_profile
# ---------------------------------------------------------------------------


def _make_client_for_profile_resolution() -> tuple[AerClient, MagicMock]:
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.has_searcher.return_value = True
    mock_registry.has_extractor.return_value = True
    mock_registry.find_searchers_for.return_value = ["auto_searcher"]
    mock_registry.find_extractors_for.return_value = ["auto_extractor"]
    client = AerClient(registry=mock_registry)
    return client, mock_registry


def test_resolve_plugin_for_profile_uses_hint():
    client, mock_registry = _make_client_for_profile_resolution()
    profile = AerProfile(
        name="p1",
        resolution=10.0,
        collections=["X"],
        plugin_hints={"search": "hinted_searcher"},
    )
    result = client._resolve_plugin_for_profile("searcher", profile)
    assert result == "hinted_searcher"
    mock_registry.has_searcher.assert_called_with("hinted_searcher")


def test_resolve_plugin_for_profile_auto_discovers():
    client, mock_registry = _make_client_for_profile_resolution()
    profile = AerProfile(name="p1", resolution=10.0, collections=["MODIS"])
    result = client._resolve_plugin_for_profile("searcher", profile)
    assert result == "auto_searcher"
    mock_registry.find_searchers_for.assert_called_with("MODIS")


def test_resolve_plugin_for_profile_hinted_not_registered():
    client, mock_registry = _make_client_for_profile_resolution()
    mock_registry.has_searcher.return_value = False
    profile = AerProfile(
        name="p1",
        resolution=10.0,
        collections=["X"],
        plugin_hints={"search": "missing_searcher"},
    )
    with pytest.raises(ValueError, match="not a registered Searcher"):
        client._resolve_plugin_for_profile("searcher", profile)


def test_resolve_plugin_for_profile_no_collections_returns_none():
    client, mock_registry = _make_client_for_profile_resolution()
    mock_registry.find_searchers_for.return_value = []
    profile = AerProfile(name="p1", resolution=10.0, collections=[])
    result = client._resolve_plugin_for_profile("searcher", profile)
    assert result is None


def test_resolve_plugin_for_profile_extract_hint():
    client, mock_registry = _make_client_for_profile_resolution()
    profile = AerProfile(
        name="p1",
        resolution=10.0,
        collections=["X"],
        plugin_hints={"extract": "hinted_extractor"},
    )
    result = client._resolve_plugin_for_profile("extractor", profile)
    assert result == "hinted_extractor"
    mock_registry.has_extractor.assert_called_with("hinted_extractor")


# ---------------------------------------------------------------------------
# search with profile plugin hints
# ---------------------------------------------------------------------------


def test_search_with_profile_plugin_hint(monkeypatch):
    """Profile-level plugin_hints['search'] should drive plugin selection."""
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.has_searcher.return_value = True
    mock_registry.find_searchers_for.return_value = []

    mock_searcher = MagicMock()
    monkeypatch.setattr("aer.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "modis"
    mock_searcher.search.return_value = valid_df
    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)
    profile = AerProfile(
        name="goes",
        resolution=1000.0,
        collections=["ABI-L1b-RadC"],
        satellite="GOES-16",
        plugin_hints={"search": "aer-search-aws-goes"},
    )
    client.search(profiles=[profile])
    mock_registry.get_searcher.assert_called_once_with("aer-search-aws-goes")


# ---------------------------------------------------------------------------
# prepare_for_extraction – target_grid_dist / target_grid_overlap forwarding
# ---------------------------------------------------------------------------


def _make_prepare_client(monkeypatch, valid_search_df):
    """Return a client whose extractor mock captures prepare_for_extraction calls."""
    mock_registry = MagicMock(spec=AerRegistry)
    monkeypatch.setattr("aer.schemas.core.AssetSchema.validate", lambda x: x)

    mock_registry.has_extractor.return_value = True
    mock_registry.find_extractors_for.return_value = ["dummy_extractor"]
    mock_extractor = MagicMock()

    task = ExtractionTask(
        assets=cast(GeoDataFrame, valid_search_df),
        profile=AerProfile(name="test", resolution=10),
        uri="test-uri",
        grid_cells=[],
    )
    mock_extractor.prepare_for_extraction.return_value = [task]
    mock_registry.get_extractor.return_value = mock_extractor

    client = AerClient(registry=mock_registry)
    return client, mock_extractor


def _make_valid_search_df():
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "MODIS"
    return valid_df


def test_prepare_for_extraction_passes_target_grid_dist(monkeypatch):
    """target_grid_dist kwarg must be forwarded to extractor.prepare_for_extraction."""
    valid_search_df = _make_valid_search_df()
    client, mock_extractor = _make_prepare_client(monkeypatch, valid_search_df)

    client.prepare_for_extraction(
        search_results=cast(GeoDataFrame, valid_search_df),
        resolution=100.0,
        uri="s3://bucket/out/",
        target_grid_dist=50_000,
    )

    call_kwargs = mock_extractor.prepare_for_extraction.call_args.kwargs
    assert call_kwargs.get("target_grid_dist") == 50_000


def test_prepare_for_extraction_passes_target_grid_overlap(monkeypatch):
    """target_grid_overlap kwarg must be forwarded to extractor.prepare_for_extraction."""
    valid_search_df = _make_valid_search_df()
    client, mock_extractor = _make_prepare_client(monkeypatch, valid_search_df)

    client.prepare_for_extraction(
        search_results=cast(GeoDataFrame, valid_search_df),
        resolution=100.0,
        uri="s3://bucket/out/",
        target_grid_overlap=True,
    )

    call_kwargs = mock_extractor.prepare_for_extraction.call_args.kwargs
    assert call_kwargs.get("target_grid_overlap") is True


def test_prepare_for_extraction_passes_none_grid_params_by_default(monkeypatch):
    """When not supplied, both grid params should be forwarded as None (defer to extractor)."""
    valid_search_df = _make_valid_search_df()
    client, mock_extractor = _make_prepare_client(monkeypatch, valid_search_df)

    client.prepare_for_extraction(
        search_results=cast(GeoDataFrame, valid_search_df),
        resolution=100.0,
        uri="s3://bucket/out/",
    )

    call_kwargs = mock_extractor.prepare_for_extraction.call_args.kwargs
    assert call_kwargs.get("target_grid_dist") is None
    assert call_kwargs.get("target_grid_overlap") is None


def test_prepare_uses_profile_extract_hint(monkeypatch):
    """prepare_for_extraction must resolve extractor from profile.plugin_hints['extract']."""
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.has_extractor.return_value = True
    mock_registry.find_extractors_for.return_value = []
    mock_extractor = MagicMock()
    mock_extractor.prepare_for_extraction.return_value = []
    mock_registry.get_extractor.return_value = mock_extractor

    monkeypatch.setattr("aer.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "MODIS"

    client = AerClient(registry=mock_registry)
    profile = AerProfile(
        name="p1",
        resolution=10.0,
        collections=["MODIS"],
        plugin_hints={"extract": "my_extractor"},
    )
    client.prepare_for_extraction(
        search_results=cast(GeoDataFrame, valid_df),
        profiles=[profile],
        uri="s3://out",
    )
    mock_registry.get_extractor.assert_called_with("my_extractor")


# ---------------------------------------------------------------------------
# extract_batches
# ---------------------------------------------------------------------------


def test_extract_batches_with_profile_hint(monkeypatch):
    """extract_batches must resolve extractor from each task's profile hint."""
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.has_extractor.return_value = True
    mock_registry.find_extractors_for.return_value = []
    mock_extractor = MagicMock()
    monkeypatch.setattr("aer.schemas.core.ArtifactSchema.validate", lambda x: x)
    empty_artifact_df = pd.DataFrame()
    mock_extractor.extract_batches.return_value = empty_artifact_df
    mock_registry.get_extractor.return_value = mock_extractor

    client = AerClient(registry=mock_registry)
    profile = AerProfile(
        name="goes",
        resolution=1000.0,
        collections=["ABI-L1b-RadC"],
        plugin_hints={"extract": "aer-extract-aws-goes"},
    )
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "ABI-L1b-RadC"
    task = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=profile,
        uri="test",
        grid_cells=[],
    )
    client.extract_batches([task])
    mock_registry.get_extractor.assert_called_once_with("aer-extract-aws-goes")
