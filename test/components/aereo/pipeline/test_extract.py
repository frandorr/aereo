"""Tests for the extract pipeline module."""

from __future__ import annotations

import geopandas as gpd
from hamilton import driver
from shapely.geometry import Point

from aereo.pipeline import extract as extract_module


def test_extract_pipeline_runs() -> None:
    """extract.py can be built into a Hamilton driver and returns artifacts_gdf."""
    dr = driver.Builder().with_modules(extract_module).build()
    mock_cogs = gpd.GeoDataFrame(
        {"id": [1, 2]}, geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326"
    )
    result = dr.execute(["artifacts_gdf"], inputs={"write_cogs": mock_cogs})
    assert "artifacts_gdf" in result
    assert len(result["artifacts_gdf"]) == 2


def test_artifacts_gdf_passthrough() -> None:
    """artifacts_gdf forwards write_cogs unchanged."""
    mock_cogs = gpd.GeoDataFrame(
        {"id": [1, 2]}, geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326"
    )
    result = extract_module.artifacts_gdf(mock_cogs)
    assert result is mock_cogs
