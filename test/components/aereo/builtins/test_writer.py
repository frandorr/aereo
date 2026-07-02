"""Tests for the write_geotiff built-in writer."""

from __future__ import annotations

from functools import partial
from typing import Any, cast

import numpy as np
import pandas as pd
import pytest
import rioxarray  # noqa: F401 — registers the ``rio`` accessor on xarray objects
import xarray as xr
from aereo.builtins import write_geotiff


@pytest.fixture(autouse=True)
def _patch_artifact_schema(monkeypatch):
    """Bypass strict ArtifactSchema validation so we can test writer logic."""
    from aereo.schemas.core import ArtifactSchema

    monkeypatch.setattr(ArtifactSchema, "validate", lambda x: x)


def _make_dataset(data_vars=None, dims=("band", "y", "x"), shape=(1, 8, 8)):
    """Return a minimal xarray.Dataset for testing."""
    if len(shape) == 2:
        shape = (1,) + shape
    coords: dict[str, Any] = {d: range(s) for d, s in zip(dims, shape)}
    if "band" in coords:
        coords["band"] = [1]
    if data_vars is None:
        data_vars = {
            "B04": (dims, np.ones(shape) * 0.3),
            "B08": (dims, np.ones(shape) * 0.5),
        }
    ds = xr.Dataset(data_vars, coords=coords)
    ds = ds.rio.write_crs("EPSG:4326")
    ds.attrs["start_time"] = pd.Timestamp("2026-01-01T12:00:00").to_pydatetime()
    ds.attrs["end_time"] = pd.Timestamp("2026-01-01T12:10:00").to_pydatetime()
    return ds


def _write_path(tmp_path) -> str:
    return str(tmp_path / "out.tif")


# ---------------------------------------------------------------------------
# Plain write (no rio_params)
# ---------------------------------------------------------------------------


def test_write_geotiff_plain_mode_driver(tmp_path):
    """Default path writes a single GTiff containing all variables as bands."""
    ds = _make_dataset()
    path = _write_path(tmp_path)
    result = write_geotiff(ds, path)

    assert result == path
    import rasterio

    with rasterio.open(path) as src:
        assert src.driver == "GTiff"
        assert src.count == 2


def test_write_geotiff_band_descriptions_match_variables(tmp_path):
    """Each raster band is labelled with its source variable name."""
    ds = _make_dataset()
    path = _write_path(tmp_path)
    write_geotiff(ds, path)

    import rasterio

    with rasterio.open(path) as src:
        assert src.count == 2
        assert src.descriptions == ("B04", "B08")

    # Reading back with rioxarray should expose all band names.
    da = rioxarray.open_rasterio(path)
    assert isinstance(da, xr.DataArray)
    assert da.attrs.get("long_name") in [("B04", "B08"), ["B04", "B08"]]


# ---------------------------------------------------------------------------
# Tiled / COG via rio_params
# ---------------------------------------------------------------------------


def test_write_geotiff_tiled_via_rio_params(tmp_path):
    """Tiling is applied to the single multi-band output file."""
    ds = _make_dataset(shape=(64, 64))
    path = _write_path(tmp_path)
    writer = partial(
        write_geotiff, rio_params={"tiled": True, "blockxsize": 32, "blockysize": 32}
    )
    writer(ds, path)

    import rasterio

    with rasterio.open(path) as src:
        assert src.profile.get("tiled", False)
        assert src.count == 2
        assert src.block_shapes[0][0] == 32
        assert src.block_shapes[0][1] == 32


# ---------------------------------------------------------------------------
# Multi-band variables
# ---------------------------------------------------------------------------


def test_write_geotiff_multiband_plain(tmp_path):
    """Multi-band variables are written as a single multi-band file."""
    ds = xr.Dataset(
        {
            "RGB": (
                ["band", "y", "x"],
                np.ones((3, 4, 4)),
            )
        },
        coords={"band": [1, 2, 3], "y": range(4), "x": range(4)},
    )
    ds = ds.rio.write_crs("EPSG:4326")
    ds.attrs["start_time"] = pd.Timestamp("2026-01-01T12:00:00").to_pydatetime()
    ds.attrs["end_time"] = pd.Timestamp("2026-01-01T12:10:00").to_pydatetime()

    path = _write_path(tmp_path)
    write_geotiff(ds, path)

    import rasterio

    with rasterio.open(path) as src:
        assert src.count == 3


def test_write_geotiff_multiband_tiled(tmp_path):
    """Multi-band variables are written as a single multi-band file with tiling via rio_params."""
    ds = xr.Dataset(
        {
            "RGB": (
                ["band", "y", "x"],
                np.ones((3, 8, 8)),
            )
        },
        coords={"band": [1, 2, 3], "y": range(8), "x": range(8)},
    )
    ds = ds.rio.write_crs("EPSG:4326")
    ds.attrs["start_time"] = pd.Timestamp("2026-01-01T12:00:00").to_pydatetime()
    ds.attrs["end_time"] = pd.Timestamp("2026-01-01T12:10:00").to_pydatetime()

    path = _write_path(tmp_path)
    writer = partial(write_geotiff, rio_params={"tiled": True})
    writer(ds, path)

    import rasterio

    with rasterio.open(path) as src:
        assert src.count == 3  # all bands in one file
        block_height: int = src.block_shapes[0][0]
        assert block_height > 1


# ---------------------------------------------------------------------------
# Pydantic fields
# ---------------------------------------------------------------------------


def test_write_geotiff_fields():
    """Only ds, path, and rio_params are declared as parameters."""
    import inspect

    sig = inspect.signature(write_geotiff)
    assert "rio_params" in sig.parameters
    assert "ds" in sig.parameters
    assert "path" in sig.parameters
    assert "task" not in sig.parameters
    assert "patch" not in sig.parameters


# ---------------------------------------------------------------------------
# rio_params forwarding
# ---------------------------------------------------------------------------


def test_write_geotiff_rio_params_forwarded(tmp_path):
    """Custom rio_params (tags and compress) are forwarded directly to to_raster."""
    ds = _make_dataset()
    path = _write_path(tmp_path)
    writer = partial(
        write_geotiff,
        rio_params={"tags": {"custom_key": "custom_val"}, "compress": "lzw"},
    )

    writer(ds, path)

    import rasterio

    with rasterio.open(path) as src:
        assert src.tags().get("custom_key") == "custom_val"
        assert src.compression.name.lower() == "lzw"


def test_write_geotiff_rejects_time_dimension(tmp_path):
    """A dataset with a time dimension raises a clear ValueError."""
    ds = xr.Dataset(
        {"B04": (["time", "y", "x"], np.ones((1, 4, 4)))},
        coords={"time": [1], "y": range(4), "x": range(4)},
    )
    ds = ds.rio.write_crs("EPSG:4326")

    path = _write_path(tmp_path)
    with pytest.raises(ValueError, match="time"):
        write_geotiff(ds, path)


def test_write_geotiff_preserves_dataset_attrs(tmp_path):
    """Dataset attributes are written as raster metadata tags and read back."""
    ds = _make_dataset()
    ds.attrs["custom_key"] = "custom_val"
    path = _write_path(tmp_path)
    write_geotiff(ds, path)

    da = cast(xr.DataArray, rioxarray.open_rasterio(path))
    assert da.attrs.get("custom_key") == "custom_val"
    # long_name should still be derived from band coordinates, not clobbered.
    assert da.attrs.get("long_name") in [("B04", "B08"), ["B04", "B08"]]

    import rasterio

    with rasterio.open(path) as src:
        assert src.tags().get("custom_key") == "custom_val"
