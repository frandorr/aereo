"""Tests for the search pipeline module."""

from __future__ import annotations

import geopandas as gpd
from hamilton import driver
from shapely.geometry import Point

from aereo.pipeline import search as search_module


def test_search_pipeline_runs() -> None:
    """search.py can be built into a Hamilton driver and returns search_results."""
    dr = driver.Builder().with_modules(search_module).build()
    mock_assets = gpd.GeoDataFrame(
        {"id": [1, 2]}, geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326"
    )
    result = dr.execute(["search_results"], inputs={"search_assets": mock_assets})
    assert "search_results" in result
    assert len(result["search_results"]) == 2


def test_search_results_passthrough() -> None:
    """search_results forwards search_assets unchanged."""
    mock_assets = gpd.GeoDataFrame(
        {"id": [1, 2]}, geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326"
    )
    result = search_module.search_results(mock_assets)
    assert result is mock_assets
