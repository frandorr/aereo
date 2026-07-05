"""Unit tests for the reproject_pyresample builtin."""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr
from odc.geo.geobox import GeoBox

from aereo.builtins.reproject import reproject_pyresample, reproject_swath


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


def test_reproject_pyresample_raw_mode():
    """Reproject a simple swath in raw mode (crs + resolution)."""
    ds = _synthetic_swath()
    out = reproject_pyresample(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
    )

    assert isinstance(out, xr.Dataset)
    assert "band" in out.data_vars
    assert tuple(out.dims) == ("y", "x")
    assert out.rio.crs is not None
    assert "spatial_ref" in out.coords


def test_reproject_pyresample_grid_mode():
    """Reproject a simple swath using a supplied GeoBox."""
    ds = _synthetic_swath()
    geobox = GeoBox.from_bbox(
        (-70.05, -40.05, -68.95, -38.95),
        crs="EPSG:4326",
        resolution=0.01,
    )
    out = reproject_pyresample(
        ds,
        geobox=geobox,
        max_distance=10_000.0,
    )

    assert isinstance(out, xr.Dataset)
    assert "band" in out.data_vars
    assert tuple(out.dims) == ("y", "x")
    assert out.rio.crs is not None


def test_reproject_pyresample_with_time_dim():
    """Reproject a swath dataset with an extra time dimension."""
    ds = _synthetic_swath(extra_dims=(3,))
    out = reproject_pyresample(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
    )

    assert out["band"].dims == ("time", "y", "x")
    assert out["band"].shape[0] == 3


def test_reproject_pyresample_missing_lons_lats():
    """Raise when the dataset lacks lons/lats."""
    ds = xr.Dataset({"band": (["y", "x"], np.ones((5, 5)))})
    with pytest.raises(
        ValueError, match="Input dataset must contain 'lons' and 'lats'"
    ):
        reproject_pyresample(ds, crs="EPSG:4326", resolution=0.01)


def test_reproject_pyresample_matches_swath_on_valid_data():
    """For fully valid synthetic data, pyresample and reproject_swath agree closely."""
    ds = _synthetic_swath((20, 20))

    out_pyresample = reproject_pyresample(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
    )
    out_swath = reproject_swath(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
    )

    # Both should have the same shape and CRS.
    assert out_pyresample["band"].shape == out_swath["band"].shape
    assert str(out_pyresample.rio.crs) == str(out_swath.rio.crs)

    # For fully valid data the nearest-neighbour mappings should be identical.
    np.testing.assert_array_equal(
        out_pyresample["band"].values, out_swath["band"].values
    )


def test_reproject_pyresample_masks_nan_source_pixels():
    """By default NaN source pixels are excluded from the pyresample search."""
    ds = _synthetic_swath((20, 20))
    values = ds["band"].values.copy()
    # Create a bow-tie-like gap across the middle rows.
    values[8:12, :] = np.nan
    ds["band"] = (["y", "x"], values)

    out = reproject_pyresample(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
    )

    # With mask_invalid=True, valid neighbours should fill the gap.
    finite_output = out["band"].values[np.isfinite(out["band"].values)]
    valid_input = values[np.isfinite(values)]
    assert set(np.unique(finite_output)).issubset(set(np.unique(valid_input)))


def test_reproject_pyresample_unmasked_nan_propagation():
    """With mask_invalid=False, pyresample propagates NaN like plain pyresample."""
    ds = _synthetic_swath((20, 20))
    values = ds["band"].values.copy()
    values[8:12, :] = np.nan
    ds["band"] = (["y", "x"], values)

    out = reproject_pyresample(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
        mask_invalid=False,
    )

    # Plain pyresample nearest does not exclude NaN source pixels.
    assert np.isnan(out["band"].values).any()


def test_reproject_pyresample_matches_swath_with_nan_data():
    """Masked pyresample and reproject_swath both avoid bow-tie NaN gaps."""
    ds = _synthetic_swath((30, 30))
    values = ds["band"].values.copy()
    # Create a bow-tie-like gap across the middle rows.
    values[12:18, :] = np.nan
    ds["band"] = (["y", "x"], values)

    out_pyresample = reproject_pyresample(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
    )
    out_swath = reproject_swath(
        ds,
        crs="EPSG:4326",
        resolution=0.01,
        max_distance=10_000.0,
    )

    # Both methods should fill the interior of the swath with valid values.
    assert np.isfinite(out_pyresample["band"].values).sum() > 0
    assert np.isfinite(out_swath["band"].values).sum() > 0
    # Neither should leave the full bow-tie gap as NaN.
    assert not np.all(np.isnan(out_pyresample["band"].values[30:70, 30:70]))
    assert not np.all(np.isnan(out_swath["band"].values[30:70, 30:70]))
