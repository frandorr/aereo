"""Unit tests for the reproject_swath builtin."""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr
from odc.geo.geobox import GeoBox

from aereo.builtins.reproject import reproject_swath


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
    with pytest.raises(ValueError, match="requires 'lons' and 'lats'"):
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
