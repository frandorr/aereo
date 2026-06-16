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


def _make_test_tiff(
    path: Path,
    bounds: tuple[float, float, float, float],
    *,
    data: np.ndarray | None = None,
    nodata: float | None = None,
) -> None:
    """Write a small single-band GeoTIFF for testing."""
    width, height = 32, 32
    transform = from_bounds(*bounds, width, height)
    if data is None:
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
        nodata=nodata,
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


def test_plot_artifact_patches_unified_normalization(
    tmp_path: Path,
) -> None:
    """All patches share the same colormap limits."""
    bounds_a = (300000.0, 5000000.0, 301000.0, 5001000.0)
    bounds_b = (301000.0, 5000000.0, 302000.0, 5001000.0)

    path_a = tmp_path / "cell_a.tif"
    path_b = tmp_path / "cell_b.tif"

    # Two patches with non-overlapping value ranges.
    _make_test_tiff(path_a, bounds_a, data=np.full((32, 32), 0.0, dtype=np.float32))
    _make_test_tiff(path_b, bounds_b, data=np.full((32, 32), 1.0, dtype=np.float32))

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(path_a), str(path_b)],
            "grid_cell": ["cell_a", "cell_b"],
            "cell_utm_footprint": [box(*bounds_a), box(*bounds_b)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    fig, ax = plot_artifact_patches(gdf, cmap="gray")
    images = ax.images
    assert len(images) == 2
    limits = [(img.norm.vmin, img.norm.vmax) for img in images]
    vmin = min(lo for lo, _hi in limits if lo is not None)
    vmax = max(hi for _lo, hi in limits if hi is not None)
    # With unified normalization both images use the same limits.
    assert all(img.norm.vmin == vmin for img in images)
    assert all(img.norm.vmax == vmax for img in images)
    fig.clf()


def test_plot_artifact_patches_vmin_vmax(
    tmp_path: Path,
) -> None:
    """Explicit vmin/vmax override the computed data range."""
    bounds = (300000.0, 5000000.0, 301000.0, 5001000.0)
    path = tmp_path / "cell.tif"
    _make_test_tiff(path, bounds, data=np.full((32, 32), 0.5, dtype=np.float32))

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(path)],
            "grid_cell": ["cell"],
            "cell_utm_footprint": [box(*bounds)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    fig, ax = plot_artifact_patches(gdf, vmin=-1.0, vmax=1.0)
    assert ax.images[0].norm.vmin == -1.0
    assert ax.images[0].norm.vmax == 1.0
    fig.clf()


def test_plot_artifact_patches_colorbar_by_default(
    sample_artifacts: gpd.GeoDataFrame,
) -> None:
    """A colorbar axis is added when colorbar=True."""
    fig, _ax = plot_artifact_patches(sample_artifacts, colorbar=True)
    assert len(fig.axes) == 2
    fig.clf()


def test_plot_artifact_patches_no_colorbar(
    sample_artifacts: gpd.GeoDataFrame,
) -> None:
    """No extra colorbar axis is added when colorbar=False."""
    fig, _ax = plot_artifact_patches(sample_artifacts, colorbar=False)
    assert len(fig.axes) == 1
    fig.clf()


def test_plot_artifact_patches_masks_nodata(
    tmp_path: Path,
) -> None:
    """Nodata pixels are masked and rendered transparently."""
    bounds = (300000.0, 5000000.0, 301000.0, 5001000.0)
    path = tmp_path / "cell.tif"

    data = np.full((32, 32), 0.5, dtype=np.float32)
    data[:16, :] = -9999.0
    _make_test_tiff(path, bounds, data=data, nodata=-9999.0)

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(path)],
            "grid_cell": ["cell"],
            "cell_utm_footprint": [box(*bounds)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    # Use ds_factor=1 so nodata pixels map one-to-one to displayed pixels.
    fig, ax = plot_artifact_patches(gdf, ds_factor=1)
    plotted = np.ma.asarray(ax.images[0].get_array())
    assert np.ma.is_masked(plotted)
    mask = np.asarray(plotted.mask)
    assert mask[:16, :].all()
    assert not mask[16:, :].any()
    fig.clf()
