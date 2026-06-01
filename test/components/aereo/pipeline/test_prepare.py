"""Tests for the prepare pipeline module."""

from __future__ import annotations

import geopandas as gpd
import pytest
from hamilton import driver
from shapely.geometry import Polygon

from aereo.grid import GridDefinition
from aereo.interfaces import GridConfig, PipelineProfile
from aereo.pipeline import prepare as prepare_module


def _make_mock_assets(
    start_time: str = "2024-01-01T00:00:00",
    collection: str = "TEST",
) -> gpd.GeoDataFrame:
    """Create a minimal AssetSchema-like GeoDataFrame."""
    geom = Polygon([(-0.1, -0.1), (0.1, -0.1), (0.1, 0.1), (-0.1, 0.1), (-0.1, -0.1)])
    return gpd.GeoDataFrame(
        {
            "start_time": [start_time],
            "collection": [collection],
            "id": ["asset-1"],
        },
        geometry=[geom],
        crs="EPSG:4326",
    )


def test_grid_definition_from_config() -> None:
    """grid_definition creates a GridDefinition from GridConfig."""
    config = GridConfig(target_grid_dist=10000)
    gd = prepare_module.grid_definition(config)
    assert isinstance(gd, GridDefinition)
    assert gd.D == 10000


def test_grid_definition_missing_dist_raises() -> None:
    """grid_definition raises ValueError when target_grid_dist is None."""
    config = GridConfig()
    with pytest.raises(ValueError, match="target_grid_dist must be set"):
        prepare_module.grid_definition(config)


def test_extraction_tasks_empty_assets() -> None:
    """extraction_tasks returns an empty list for empty assets."""
    profile = PipelineProfile(name="test", resolution=100.0)
    config = GridConfig(target_grid_dist=10000)
    result = prepare_module.extraction_tasks(
        assets=gpd.GeoDataFrame(),
        grid_config=config,
        aoi=None,
        profile=profile,
        uri="s3://test/",
    )
    assert result == []


def test_extraction_tasks_missing_uri_raises() -> None:
    """extraction_tasks raises ValueError when uri is None."""
    profile = PipelineProfile(name="test", resolution=100.0)
    config = GridConfig(target_grid_dist=10000)
    with pytest.raises(ValueError, match="uri must be provided"):
        prepare_module.extraction_tasks(
            assets=_make_mock_assets(),
            grid_config=config,
            aoi=None,
            profile=profile,
            uri=None,
        )


def test_extraction_tasks_runs() -> None:
    """extraction_tasks produces tasks from mock assets."""
    profile = PipelineProfile(
        name="test", resolution=100.0, collections={"TEST": ["var1"]}
    )
    config = GridConfig(target_grid_dist=10000)
    assets = _make_mock_assets()
    result = prepare_module.extraction_tasks(
        assets=assets,
        grid_config=config,
        aoi=None,
        profile=profile,
        uri="s3://test/",
        cells_per_task=10,
    )
    assert isinstance(result, list)
    assert len(result) > 0
    task = result[0]
    assert task.uri == "s3://test/"
    assert task.profile.name == "test"
    assert len(task.grid_cells) > 0


def test_extraction_tasks_with_aoi() -> None:
    """extraction_tasks filters by AOI when provided."""
    profile = PipelineProfile(
        name="test", resolution=100.0, collections={"TEST": ["var1"]}
    )
    config = GridConfig(target_grid_dist=10000)
    assets = _make_mock_assets()
    aoi = Polygon(
        [(-0.05, -0.05), (0.05, -0.05), (0.05, 0.05), (-0.05, 0.05), (-0.05, -0.05)]
    )
    result = prepare_module.extraction_tasks(
        assets=assets,
        grid_config=config,
        aoi=aoi,
        profile=profile,
        uri="s3://test/",
    )
    assert isinstance(result, list)


def test_prepare_pipeline_runs() -> None:
    """prepare.py can be built into a Hamilton driver and returns extraction_tasks."""
    dr = driver.Builder().with_modules(prepare_module).build()
    profile = PipelineProfile(
        name="test", resolution=100.0, collections={"TEST": ["var1"]}
    )
    config = GridConfig(target_grid_dist=10000)
    assets = _make_mock_assets()
    result = dr.execute(
        ["extraction_tasks"],
        inputs={
            "assets": assets,
            "grid_config": config,
            "aoi": None,
            "profile": profile,
            "uri": "s3://test/",
        },
    )
    assert "extraction_tasks" in result
    assert len(result["extraction_tasks"]) > 0
