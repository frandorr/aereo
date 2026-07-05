"""Unit tests for the reproject_swath builtin."""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr
from odc.geo.geobox import GeoBox

from aereo.builtins.reproject import _build_cached_swath_kdtree, reproject_swath


def _synthetic_swath(
    shape: tuple[int, int] = (10, 10),
    extra_dims: tuple[int, ...] = (),
) -> xr.Dataset:
    """Create a synthetic swath dataset for testing."""
    rows, cols = shape
    lons = np.linspace(-70.0, -69.0, cols)
    lats = np.linspace(-40.0, -39.0, rows)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    base_values = np.arange(rows * cols, dtype=np.float64).reshape(shape)
    if extra_dims:
        values = np.stack([base_values + i for i in range(extra_dims[0])], axis=0)
        dims = ("time", "y", "x")
    else:
        values = base_values
        dims = ("y", "x")

    return xr.Dataset(
        {
            "lons": (["y", "x"], lon_grid),
            "lats": (["y", "x"], lat_grid),
            "band": (dims, values),
        },
        attrs={"test_attr": "value"},
    )


def test_reproject_swath_raw_mode():
    """Reproject a simple swath in raw mode (crs + resolution)."""
    ds = _synthetic_swath()
    out = reproject_swath(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        buffer=0.05,
        max_distance=10_000.0,
    )

    assert isinstance(out, xr.Dataset)
    assert "band" in out.data_vars
    assert tuple(out.dims) == ("y", "x")
    assert out.rio.crs is not None
    assert "spatial_ref" in out.coords
    # Every unique swath value should appear somewhere in the nearest-neighbour output.
    assert set(np.unique(out["band"].values)).issuperset(
        set(np.unique(ds["band"].values))
    )


def test_reproject_swath_grid_mode():
    """Reproject a simple swath using a supplied GeoBox."""
    ds = _synthetic_swath()
    geobox = GeoBox.from_bbox(
        (-70.05, -40.05, -68.95, -38.95),
        crs="EPSG:4326",
        resolution=0.01,
    )
    out = reproject_swath(
        ds,
        geobox=geobox,
        buffer=0.05,
        max_distance=10_000.0,
    )

    assert isinstance(out, xr.Dataset)
    assert "band" in out.data_vars
    assert tuple(out.dims) == ("y", "x")
    assert out.rio.crs is not None


def test_reproject_swath_with_time_dim():
    """Reproject a swath dataset with an extra time dimension."""
    ds = _synthetic_swath(extra_dims=(3,))
    out = reproject_swath(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        buffer=0.05,
        max_distance=10_000.0,
    )

    assert out["band"].dims == ("time", "y", "x")
    assert out["band"].shape[0] == 3
    for t in range(3):
        assert set(np.unique(out["band"].values[t])).issuperset(
            set(np.unique(ds["band"].values[t]))
        )


def test_reproject_swath_missing_lons_lats():
    """Raise when the dataset lacks lons/lats."""
    ds = xr.Dataset({"band": (["y", "x"], np.ones((5, 5)))})
    with pytest.raises(
        ValueError, match="Input dataset must contain 'lons' and 'lats'"
    ):
        reproject_swath(ds, crs="EPSG:4326", resolution=0.01)


def test_reproject_swath_missing_target_params():
    """Raise when neither geobox nor crs+resolution are provided."""
    ds = _synthetic_swath()
    with pytest.raises(
        ValueError, match="either 'geobox' or both 'crs' and 'resolution'"
    ):
        reproject_swath(ds)


def test_reproject_swath_fill_value_and_mask():
    """Distant target pixels are filled with fill_value."""
    ds = _synthetic_swath((10, 10))
    out = reproject_swath(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        buffer=0.0,
        max_distance=1.0,
        fill_value=-999.0,
    )

    assert np.any(out["band"].values == -999.0)


def test_reproject_swath_caches_kdtree_across_geoboxes():
    """The same swath reused with different geoboxes only builds one KDTree."""
    _build_cached_swath_kdtree.cache_clear()
    ds = _synthetic_swath((20, 20))

    geobox_a = GeoBox.from_bbox(
        (-70.05, -40.05, -69.55, -39.55),
        crs="EPSG:4326",
        resolution=0.01,
    )
    geobox_b = GeoBox.from_bbox(
        (-69.55, -40.05, -69.05, -39.55),
        crs="EPSG:4326",
        resolution=0.01,
    )

    out_a = reproject_swath(ds, geobox=geobox_a, max_distance=10_000.0)
    cache_after_first = _build_cached_swath_kdtree.cache_info().currsize
    out_b = reproject_swath(ds, geobox=geobox_b, max_distance=10_000.0)
    cache_after_second = _build_cached_swath_kdtree.cache_info().currsize

    assert cache_after_first == 1
    assert cache_after_second == 1
    assert isinstance(out_a, xr.Dataset)
    assert isinstance(out_b, xr.Dataset)

    _build_cached_swath_kdtree.cache_clear()


def test_reproject_swath_skips_nan_data_pixels():
    """NaN data pixels are excluded from the nearest-neighbour search.

    This reproduces the VIIRS bow-tie situation: some source pixels are NaN,
    but valid neighbours exist nearby. The output should pick the nearest valid
    neighbour rather than propagating the NaN.
    """
    ds = _synthetic_swath((20, 20))
    values = ds["band"].values.copy()
    # Create a bow-tie-like gap across the middle rows.
    values[8:12, :] = np.nan
    ds["band"] = (["y", "x"], values)

    out = reproject_swath(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
    )

    output = out["band"].values
    # The interior of the output should contain finite values from valid neighbours.
    assert np.isfinite(output).sum() > 0
    # Every finite output value must come from a finite input value.
    finite_output = output[np.isfinite(output)]
    valid_input = values[np.isfinite(values)]
    assert set(np.unique(finite_output)).issubset(set(np.unique(valid_input)))


def test_reproject_swath_caches_kdtree_per_mask():
    """Variables with different NaN masks get separate cached trees."""
    _build_cached_swath_kdtree.cache_clear()
    ds = _synthetic_swath((10, 10))
    ds["band_a"] = ds["band"]
    ds["band_b"] = ds["band"].copy()
    ds["band_b"].values[0:5, :] = np.nan

    out = reproject_swath(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
    )

    # band and band_a share the all-valid mask; band_b has its own masked tree.
    assert _build_cached_swath_kdtree.cache_info().currsize == 2
    assert "band_a" in out.data_vars
    assert "band_b" in out.data_vars

    _build_cached_swath_kdtree.cache_clear()


def test_reproject_swath_all_nan_data_emits_fill_value():
    """A variable whose data is entirely NaN is remapped to fill_value."""
    ds = _synthetic_swath((10, 10))
    ds["band"] = (["y", "x"], np.full((10, 10), np.nan))

    out = reproject_swath(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
        fill_value=-999.0,
    )

    assert "band" in out.data_vars
    assert np.all(out["band"].values == -999.0)
