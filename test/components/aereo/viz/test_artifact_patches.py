"""Tests for the plot_artifact_patches helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import box

from aereo.spatial import reproject_geom
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


def _make_test_tiff_multiband(
    path: Path,
    bounds: tuple[float, float, float, float],
    *,
    data: np.ndarray | None = None,
    nodata: float | None = None,
) -> None:
    """Write a small 3-band GeoTIFF for testing RGB plots."""
    width, height = 32, 32
    transform = from_bounds(*bounds, width, height)
    if data is None:
        data = np.ones((3, height, width), dtype=np.float32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=3,
        dtype=data.dtype,
        crs="EPSG:32633",
        transform=transform,
        nodata=nodata,
    ) as dst:
        for i in range(3):
            dst.write(data[i], i + 1)


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


def test_plot_artifact_patches_rgb(
    tmp_path: Path,
) -> None:
    """Three bands can be plotted as an RGB composite."""
    bounds = (300000.0, 5000000.0, 301000.0, 5001000.0)
    path = tmp_path / "cell_rgb.tif"

    data = np.stack(
        [
            np.full((32, 32), 0.0, dtype=np.float32),
            np.full((32, 32), 0.5, dtype=np.float32),
            np.full((32, 32), 1.0, dtype=np.float32),
        ]
    )
    _make_test_tiff_multiband(path, bounds, data=data)

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(path)],
            "grid_cell": ["cell_rgb"],
            "cell_utm_footprint": [box(*bounds)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    fig, ax = plot_artifact_patches(gdf, bands=[1, 2, 3])
    assert len(ax.images) == 1
    # RGB images have shape (H, W, 3) and no colorbar axis.
    rgb_array = ax.images[0].get_array()
    assert rgb_array is not None
    assert rgb_array.shape[-1] == 3
    assert len(fig.axes) == 1
    fig.clf()


def test_plot_artifact_patches_single_band_int(
    sample_artifacts: gpd.GeoDataFrame,
) -> None:
    """An integer band index is accepted for single-band plots."""
    fig, ax = plot_artifact_patches(sample_artifacts, bands=1, cmap="gray")
    assert len(ax.images) == 2
    fig.clf()


def test_plot_artifact_patches_rgb_ignores_cmap_and_colorbar(
    tmp_path: Path,
) -> None:
    """RGB mode ignores cmap, vmin/vmax and does not add a colorbar."""
    bounds = (300000.0, 5000000.0, 301000.0, 5001000.0)
    path = tmp_path / "cell_rgb.tif"
    _make_test_tiff_multiband(path, bounds)

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(path)],
            "grid_cell": ["cell_rgb"],
            "cell_utm_footprint": [box(*bounds)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    fig, _ax = plot_artifact_patches(
        gdf,
        bands=[1, 2, 3],
        cmap="viridis",
        vmin=-100.0,
        vmax=100.0,
        colorbar=True,
    )
    # No colorbar axis is created in RGB mode.
    assert len(fig.axes) == 1
    fig.clf()


def test_plot_artifact_patches_rgb_masks_nodata(
    tmp_path: Path,
) -> None:
    """Nodata pixels in RGB rasters are rendered transparently."""
    bounds = (300000.0, 5000000.0, 301000.0, 5001000.0)
    path = tmp_path / "cell_rgb_nodata.tif"

    data = np.ones((3, 32, 32), dtype=np.float32)
    data[:, :16, :] = -9999.0
    _make_test_tiff_multiband(path, bounds, data=data, nodata=-9999.0)

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(path)],
            "grid_cell": ["cell_rgb"],
            "cell_utm_footprint": [box(*bounds)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    fig, ax = plot_artifact_patches(gdf, bands=[1, 2, 3], ds_factor=1)
    rgb = np.ma.asarray(ax.images[0].get_array())
    mask = np.asarray(rgb.mask)
    assert mask[:16, :, :].all()
    assert not mask[16:, :, :].any()
    fig.clf()


def test_plot_artifact_patches_percentile_stretch(
    tmp_path: Path,
) -> None:
    """Percentile stretch clips outliers and uses 2nd/98th percentiles."""
    bounds = (300000.0, 5000000.0, 301000.0, 5001000.0)
    path = tmp_path / "cell.tif"

    data = np.zeros((32, 32), dtype=np.float32)
    data[:, :16] = 1.0
    data[0, 0] = 100.0  # outlier
    _make_test_tiff(path, bounds, data=data)

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(path)],
            "grid_cell": ["cell"],
            "cell_utm_footprint": [box(*bounds)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    fig, ax = plot_artifact_patches(gdf, stretch="percentile")
    # Percentile stretch should ignore the 100 outlier and stay near [0, 1].
    assert cast(float, ax.images[0].norm.vmin) < 0.1
    assert 0.9 < cast(float, ax.images[0].norm.vmax) < 2.0
    fig.clf()


def test_plot_artifact_patches_zscore_stretch(
    tmp_path: Path,
) -> None:
    """Z-score stretch keeps values as z-scores and defaults to +/- 2."""
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

    fig, ax = plot_artifact_patches(gdf, stretch="zscore")
    assert ax.images[0].norm.vmin == -2.0
    assert ax.images[0].norm.vmax == 2.0
    fig.clf()


def test_plot_artifact_patches_rgb_zscore_stretch(
    tmp_path: Path,
) -> None:
    """Z-score stretch works for RGB composites."""
    bounds = (300000.0, 5000000.0, 301000.0, 5001000.0)
    path = tmp_path / "cell_rgb_zscore.tif"
    _make_test_tiff_multiband(path, bounds)

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(path)],
            "grid_cell": ["cell_rgb"],
            "cell_utm_footprint": [box(*bounds)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    fig, ax = plot_artifact_patches(gdf, bands=[1, 2, 3], stretch="zscore")
    assert len(ax.images) == 1
    rgb_array = ax.images[0].get_array()
    assert rgb_array is not None
    assert rgb_array.shape[-1] == 3
    fig.clf()


def test_plot_artifact_patches_reuses_shared_uri(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple artifact rows pointing at the same URI are loaded and drawn only once."""
    bounds_a = (300000.0, 5000000.0, 301000.0, 5001000.0)
    bounds_b = (301000.0, 5000000.0, 302000.0, 5001000.0)
    shared_path = tmp_path / "shared.tif"
    _make_test_tiff(shared_path, bounds_a)

    open_calls: list[Any] = []
    original_open = rasterio.open

    def counting_open(*args: Any, **kwargs: Any) -> Any:
        open_calls.append(args)
        return original_open(*args, **kwargs)

    monkeypatch.setattr(rasterio, "open", counting_open)

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(shared_path), str(shared_path)],
            "grid_cell": ["cell_a", "cell_b"],
            "cell_utm_footprint": [box(*bounds_a), box(*bounds_b)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    fig, ax = plot_artifact_patches(gdf)
    assert len(open_calls) == 1
    assert len(ax.images) == 1
    fig.clf()


def test_plot_artifact_patches_aoi_overlay(
    tmp_path: Path,
) -> None:
    """An AOI geometry in EPSG:4326 can be overlaid on the patches."""
    import matplotlib.colors as mcolors

    bounds = (300000.0, 5000000.0, 301000.0, 5001000.0)
    path = tmp_path / "cell.tif"
    _make_test_tiff(path, bounds)

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(path)],
            "grid_cell": ["cell"],
            "cell_utm_footprint": [box(*bounds)],
            "cell_utm_crs": ["EPSG:32633"],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    aoi_utm = box(bounds[0] + 100, bounds[1] + 100, bounds[2] - 100, bounds[3] - 100)
    aoi_wgs84 = reproject_geom(aoi_utm, src_epsg="EPSG:32633", dst_epsg="EPSG:4326")

    fig, ax = plot_artifact_patches(gdf, aoi=aoi_wgs84, aoi_edgecolor="lime")
    aoi_collections = [
        c
        for c in ax.collections
        if np.allclose(
            c.get_edgecolor(),
            mcolors.to_rgba("lime"),
        )
    ]
    assert len(aoi_collections) > 0
    fig.clf()


def test_plot_artifact_patches_aoi_geodataframe(
    tmp_path: Path,
) -> None:
    """An AOI GeoDataFrame is overlaid using its own CRS."""
    bounds = (300000.0, 5000000.0, 301000.0, 5001000.0)
    path = tmp_path / "cell.tif"
    _make_test_tiff(path, bounds)

    gdf = gpd.GeoDataFrame(
        {
            "uri": [str(path)],
            "grid_cell": ["cell"],
            "cell_utm_footprint": [box(*bounds)],
            "cell_utm_crs": ["EPSG:32633"],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    aoi_utm = box(bounds[0] + 100, bounds[1] + 100, bounds[2] - 100, bounds[3] - 100)
    aoi_gdf = gpd.GeoDataFrame(geometry=[aoi_utm], crs="EPSG:32633")

    fig, ax = plot_artifact_patches(gdf, aoi=aoi_gdf, aoi_edgecolor="lime")
    assert fig is not None
    assert ax is not None
    fig.clf()


def test_plot_artifact_patches_aoi_missing_crs_raises(
    sample_artifacts: gpd.GeoDataFrame,
) -> None:
    """Passing aoi without cell_utm_crs raises a clear error."""
    aoi = box(8.0, 45.0, 9.0, 46.0)
    with pytest.raises(ValueError, match="cell_utm_crs"):
        plot_artifact_patches(sample_artifacts, aoi=aoi)


def test_plot_artifact_patches_overlay_on_existing_ax(
    tmp_path: Path,
) -> None:
    """Passing an existing axes plots the mosaic on that axes for overlay."""
    import matplotlib.pyplot as plt

    bounds_a = (300000.0, 5000000.0, 301000.0, 5001000.0)
    bounds_b = (301000.0, 5000000.0, 302000.0, 5001000.0)

    path_a = tmp_path / "cell_a.tif"
    path_b = tmp_path / "cell_b.tif"
    _make_test_tiff(path_a, bounds_a, data=np.ones((32, 32), dtype=np.float32) * 10)
    _make_test_tiff(path_b, bounds_b, data=np.ones((32, 32), dtype=np.float32) * 20)

    gdf_base = gpd.GeoDataFrame(
        {
            "uri": [str(path_a), str(path_b)],
            "grid_cell": ["cell_a", "cell_b"],
            "cell_utm_footprint": [box(*bounds_a), box(*bounds_b)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    path_c = tmp_path / "cell_c.tif"
    _make_test_tiff(path_c, bounds_a, data=np.ones((32, 32), dtype=np.float32) * 30)
    gdf_overlay = gpd.GeoDataFrame(
        {
            "uri": [str(path_c)],
            "grid_cell": ["cell_c"],
            "cell_utm_footprint": [box(*bounds_a)],
        },
        geometry="cell_utm_footprint",
        crs="EPSG:32633",
    )

    fig, ax = plot_artifact_patches(gdf_base, cmap="Grays")
    base_images = len(ax.images)
    assert base_images > 0

    fig2, ax2 = plot_artifact_patches(gdf_overlay, ax=ax, alpha=0.5, cmap="Greens")
    assert fig2 is fig
    assert ax2 is ax
    assert len(ax.images) == base_images + 1
    assert ax.images[-1].get_alpha() == pytest.approx(0.5)

    plt.close(fig)
