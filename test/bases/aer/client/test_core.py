from unittest.mock import MagicMock
import pytest
import pandas as pd
from shapely.geometry import Point

from aer.registry.core import AerRegistry
from aer.client.core import AerClient, FailureMode, normalize_geometry
from aer.schemas.core import AssetSchema, ArtifactSchema


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
    search_context = client.search(
        collections=["MODIS"], intersects={"type": "Point", "coordinates": [0, 0]}
    )

    # Validations
    assert len(search_context.search_results) == 2
    mock_registry.find_searchers_for.assert_called_with("MODIS")
    mock_registry.get_searcher.assert_called_with("dummy_searcher")
    mock_searcher.search.assert_called_once()
    assert isinstance(search_context.search_results, pd.DataFrame)


def test_client_search_normalizes_collections(monkeypatch):
    """Verify that collection names are normalized to lowercase before being passed to plugins."""
    mock_registry = MagicMock(spec=AerRegistry)

    # Setup mock registry to return valid dummy data for lowercase collection name
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    monkeypatch.setattr("aer.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "GOES-Abi1"
    mock_searcher.search.return_value = valid_df

    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)

    # Search with uppercase collection name - should be normalized to lowercase
    client.search(
        collections=["GOES-Abi1"],
        start_datetime=None,
        end_datetime=None,
    )

    # The plugin should receive lowercase collection name
    call_args = mock_searcher.search.call_args
    assert call_args is not None
    passed_collections = list(call_args.kwargs.get("collections", []))
    assert "goes-abi1" in passed_collections, (
        f"Expected lowercase collection, got: {passed_collections}"
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
    search_ctx = client.search(
        collections=["MODIS"], failure_mode=FailureMode.BEST_EFFORT
    )
    assert len(search_ctx.search_results) == 0


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
    # It must prepare and return a list of dfs
    mock_extractor.prepare_for_extraction.return_value = [valid_search_df]
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
    final_df = client.run_pipeline(collections=["MODIS"])

    assert len(final_df) == 1
    mock_searcher.search.assert_called_once()
    mock_extractor.prepare_for_extraction.assert_called_once()
    mock_extractor.extract_batches.assert_called_once()
