"""Tests for the plot_artifact_patches helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import box

from aereo.viz import plot_artifact_patches


def _make_test_tiff(path: Path, bounds: tuple[float, float, float, float]) -> None:
    """Write a small single-band GeoTIFF for testing."""
    width, height = 32, 32
    transform = from_bounds(*bounds, width, height)
    data = np.ones((height, width), dtype=np.float32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=data.dtype,
        crs="EPSG:32633",
        transform=transform,
    ) as dst:
        dst.write(data, 1)


@pytest.fixture
def sample_artifacts(tmp_path: Path) -> gpd.GeoDataFrame:
    """Return a GeoDataFrame with two artifacts and their footprints."""
    bounds_a = (300000.0, 5000000.0, 301000.0, 5001000.0)
    bounds_b = (301000.0, 5000000.0, 302000.0, 5001000.0)

    path_a = tmp_path / "cell_a.tif"
    path_b = tmp_path / "cell_b.tif"
    _make_test_tiff(path_a, bounds_a)
    _make_test_tiff(path_b, bounds_b)

    data: dict[str, Any] = {
        "uri": [str(path_a), str(path_b)],
        "grid_cell": ["cell_a", "cell_b"],
        "cell_utm_footprint": [box(*bounds_a), box(*bounds_b)],
    }
    return gpd.GeoDataFrame(data, geometry="cell_utm_footprint", crs="EPSG:32633")


def test_plot_artifact_patches_returns_fig_ax(
    sample_artifacts: gpd.GeoDataFrame,
) -> None:
    """The helper returns a matplotlib figure and axes."""
    fig, ax = plot_artifact_patches(sample_artifacts)
    assert fig is not None
    assert ax is not None
    fig.clf()


def test_plot_artifact_patches_without_annotations(
    sample_artifacts: gpd.GeoDataFrame,
) -> None:
    """Annotations can be disabled."""
    fig, ax = plot_artifact_patches(sample_artifacts, annotate_cells=False)
    assert fig is not None
    fig.clf()


def test_plot_artifact_patches_empty_raises() -> None:
    """An empty GeoDataFrame raises a clear ValueError."""
    empty = gpd.GeoDataFrame(
        columns=["uri", "grid_cell", "cell_utm_footprint"],
        geometry="cell_utm_footprint",
    )
    with pytest.raises(ValueError, match="empty"):
        plot_artifact_patches(empty)


def test_plot_artifact_patches_missing_columns_raises() -> None:
    """Missing required columns raises a clear ValueError."""
    gdf = gpd.GeoDataFrame(
        {"uri": ["x.tif"]}, geometry=gpd.GeoSeries([], dtype="geometry")
    )
    with pytest.raises(ValueError, match="missing required columns"):
        plot_artifact_patches(gdf)
