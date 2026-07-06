"""Unit tests for the reproject_swath builtin (pyresample-based)."""

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


def test_reproject_swath_masks_nan_source_pixels():
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


def test_reproject_swath_unmasked_nan_propagation():
    """With mask_invalid=False, pyresample propagates NaN like plain pyresample."""
    ds = _synthetic_swath((20, 20))
    values = ds["band"].values.copy()
    values[8:12, :] = np.nan
    ds["band"] = (["y", "x"], values)

    out = reproject_swath(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
        mask_invalid=False,
    )

    # Plain pyresample nearest does not exclude NaN source pixels.
    assert np.isnan(out["band"].values).any()


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


def test_reproject_pyresample_alias():
    """reproject_pyresample is kept as a deprecated alias."""
    from aereo.builtins.reproject import reproject_pyresample

    ds = _synthetic_swath()
    out = reproject_pyresample(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
    )

    assert isinstance(out, xr.Dataset)
    assert "band" in out.data_vars
