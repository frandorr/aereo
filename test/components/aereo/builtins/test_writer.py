"""Tests for the WriteGeoTIFF built-in writer."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
import rioxarray  # noqa: F401 — registers the ``rio`` accessor on xarray objects
import xarray as xr
from shapely.geometry import Polygon, box

from aereo.builtins import WriteGeoTIFF
from aereo.grid import ExtractionPatch
from aereo.interfaces.core import ExtractionTask, GridConfig, PatchConfig
from aereo.schemas.core import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame


@pytest.fixture(autouse=True)
def _patch_artifact_schema(monkeypatch):
    """Bypass strict ArtifactSchema validation so we can test writer logic."""
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


def _make_task(tmp_path):
    """Return a minimal ExtractionTask for writer tests."""
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    valid_df["collection"] = "C1"
    valid_df["start_time"] = pd.Timestamp("2026-01-01T12:00:00")
    valid_df["end_time"] = pd.Timestamp("2026-01-01T12:10:00")

    grid_config = GridConfig(target_grid_dist=50_000)
    patch_config = PatchConfig(resolution=10.0)
    patch = ExtractionPatch(
        id="test_cell",
        d=10_000,
        cell_geometry=box(-70.5, -33.5, -70.0, -33.0),
        resolution=10.0,
        margin=0.0,
        padding=0,
        conform_to=None,
    )
    return ExtractionTask(
        assets=GeoDataFrame(valid_df),
        pipeline=[],
        uri=str(tmp_path),
        patches=[patch],
        grid_config=grid_config,
        patch_config=patch_config,
    )


# ---------------------------------------------------------------------------
# Plain write (no rio_params)
# ---------------------------------------------------------------------------


def test_write_geotiff_plain_mode_driver(tmp_path):
    """Default path writes a GTiff."""
    ds = _make_dataset()
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer(ds, task, task.patches[0])

    assert len(result) == 2
    for _, row in result.iterrows():
        import rasterio

        with rasterio.open(row["uri"]) as src:
            assert src.driver == "GTiff"


def test_write_geotiff_plain_mode_returns_artifacts(tmp_path):
    """Plain path returns correct artifact metadata."""
    ds = _make_dataset()
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer(ds, task, task.patches[0])

    assert set(result["id"]) == {"test_cell_B04_0", "test_cell_B08_0"}
    assert bool((result["grid_cell"] == "test_cell").all())


# ---------------------------------------------------------------------------
# Tiled / COG via rio_params
# ---------------------------------------------------------------------------


def test_write_geotiff_tiled_via_rio_params(tmp_path):
    """Tiling is applied when requested through rio_params."""
    ds = _make_dataset(shape=(64, 64))
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF(
        rio_params={"tiled": True, "blockxsize": 32, "blockysize": 32}
    )
    result = writer(ds, task, task.patches[0])

    import rasterio

    for _, row in result.iterrows():
        with rasterio.open(row["uri"]) as src:
            assert src.profile.get("tiled", False)
            assert src.block_shapes[0][0] == 32
            assert src.block_shapes[0][1] == 32


# ---------------------------------------------------------------------------
# Multi-band variables
# ---------------------------------------------------------------------------


def test_write_geotiff_multiband_plain(tmp_path):
    """Multi-band variables are split per band."""
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

    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer(ds, task, task.patches[0])

    assert len(result) == 3
    assert set(result["id"]) == {
        "test_cell_RGB_0",
        "test_cell_RGB_1",
        "test_cell_RGB_2",
    }


def test_write_geotiff_multiband_tiled(tmp_path):
    """Multi-band variables are split per band with tiling via rio_params."""
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

    task = _make_task(tmp_path)
    writer = WriteGeoTIFF(rio_params={"tiled": True})
    result = writer(ds, task, task.patches[0])

    import rasterio

    assert len(result) == 3
    for _, row in result.iterrows():
        with rasterio.open(row["uri"]) as src:
            block_height: int = src.block_shapes[0][0]
            assert block_height > 1


# ---------------------------------------------------------------------------
# Pydantic fields
# ---------------------------------------------------------------------------


def test_write_geotiff_fields():
    """Only rio_params is declared."""
    assert "rio_params" in WriteGeoTIFF.model_fields


# ---------------------------------------------------------------------------
# rio_params forwarding
# ---------------------------------------------------------------------------


def test_write_geotiff_rio_params_forwarded(tmp_path):
    """Custom rio_params (tags and compress) are forwarded directly to to_raster."""
    ds = _make_dataset()
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF(
        rio_params={"tags": {"custom_key": "custom_val"}, "compress": "lzw"}
    )

    result = writer(ds, task, task.patches[0])

    import rasterio

    assert len(result) > 0
    for _, row in result.iterrows():
        with rasterio.open(row["uri"]) as src:
            assert src.tags().get("custom_key") == "custom_val"
            assert src.compression.name.lower() == "lzw"


def test_write_geotiff_missing_time_bounds_raises(tmp_path):
    """A dataset with no time dim and no attrs raises a clear ValueError."""
    ds = xr.Dataset(
        {"B04": (["band", "y", "x"], np.ones((1, 4, 4)))},
        coords={"band": [1], "y": range(4), "x": range(4)},
    )
    ds = ds.rio.write_crs("EPSG:4326")

    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    with pytest.raises(ValueError, match="start_time.*end_time"):
        writer(ds, task, task.patches[0])
