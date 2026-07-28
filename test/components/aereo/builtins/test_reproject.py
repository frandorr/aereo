"""Unit tests for the reproject_odc builtin."""

from __future__ import annotations

import numpy as np
import pytest
import rioxarray  # noqa: F401  (ensures the .rio accessor is registered)
import xarray as xr

from aereo.builtins.reproject import reproject_odc


def _synthetic_latlon_ds() -> xr.Dataset:
    """Create a small EPSG:4326 dataset (~0.5 deg x 0.5 deg around 36S, 61W)."""
    y = np.linspace(-36.0, -35.5, 6)
    x = np.linspace(-61.0, -60.5, 6)
    values = np.arange(y.size * x.size, dtype=np.float64).reshape(y.size, x.size)
    da = xr.DataArray(values, dims=("y", "x"), coords={"y": y, "x": x})
    return da.to_dataset(name="band").rio.write_crs("EPSG:4326")


def test_reproject_odc_crs_resolution_from_epsg4326():
    """Raw-mode reprojection must warp the source bounds into the target CRS.

    Regression test: previously the EPSG:4326 degree bounds were passed
    directly to ``GeoBox.from_bbox`` with a metre-based CRS, collapsing the
    output to a single pixel.
    """
    ds = _synthetic_latlon_ds()
    out = reproject_odc(ds, crs="EPSG:32720", resolution=1000)

    assert out.rio.crs.to_epsg() == 32720
    # ~0.5 deg at this latitude is tens of kilometres, so the output must
    # span many 1 km pixels, not collapse to 1x1.
    assert out.sizes["x"] > 10
    assert out.sizes["y"] > 10
    assert not np.isnan(out["band"].values).all()


def test_reproject_odc_accepts_bare_epsg_number():
    """Bare EPSG numbers as strings ("32720") are normalized before use."""
    ds = _synthetic_latlon_ds()
    out = reproject_odc(ds, crs="32720", resolution=1000)

    assert out.rio.crs.to_epsg() == 32720
    assert out.sizes["x"] > 10
    assert out.sizes["y"] > 10


def test_reproject_odc_requires_crs_and_resolution():
    ds = _synthetic_latlon_ds()
    with pytest.raises(ValueError, match="crs.*resolution"):
        reproject_odc(ds)
    with pytest.raises(ValueError, match="crs.*resolution"):
        reproject_odc(ds, crs="EPSG:32720")
