"""Tests for the WriteGeoTIFF built-in writer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import rioxarray  # noqa: F401 — registers the ``rio`` accessor on xarray objects
import xarray as xr
from shapely.geometry import Polygon

from aereo.builtins import WriteGeoTIFF
from aereo.grid import GridCell
from aereo.interfaces.core import AereoProfile, ExtractionTask, GridConfig
from aereo.schemas.core import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame


@pytest.fixture(autouse=True)
def _patch_artifact_schema(monkeypatch):
    """Bypass strict ArtifactSchema validation so we can test writer logic."""
    monkeypatch.setattr(ArtifactSchema, "validate", lambda x: x)


def _make_dataset(data_vars=None, dims=("y", "x"), shape=(8, 8)):
    """Return a minimal AereoDataset for testing."""
    coords = {d: range(s) for d, s in zip(dims, shape)}
    if data_vars is None:
        data_vars = {
            "B04": (dims, np.ones(shape) * 0.3),
            "B08": (dims, np.ones(shape) * 0.5),
        }
    ds = xr.Dataset(data_vars, coords=coords)
    ds = ds.rio.write_crs("EPSG:4326")
    return ds


def _make_task(tmp_path, profile=None):
    """Return a minimal ExtractionTask for writer tests."""
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    valid_df["collection"] = "C1"
    valid_df["start_time"] = pd.Timestamp("2026-01-01T12:00:00")
    valid_df["end_time"] = pd.Timestamp("2026-01-01T12:10:00")

    grid_config = GridConfig(target_grid_dist=50_000)
    cell = GridCell(
        d=10_000,
        geom=Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
        is_primary=True,
        cell_id="test_cell",
    )
    return ExtractionTask(
        assets=GeoDataFrame(valid_df),
        profile=profile or AereoProfile(name="test", resolution=100.0),
        uri=str(tmp_path),
        grid_cells=[cell],
        grid_config=grid_config,
    )


# ---------------------------------------------------------------------------
# Plain GeoTIFF path (backward compatibility)
# ---------------------------------------------------------------------------


def test_write_geotiff_plain_mode_driver(tmp_path):
    """Default path writes plain GTiff, not COG."""
    ds = _make_dataset()
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer.write(ds, task, task.grid_cells[0], {})

    assert len(result) == 2
    for _, row in result.iterrows():
        import rasterio

        with rasterio.open(row["path"]) as src:
            assert src.driver == "GTiff"
            assert not src.is_tiled


def test_write_geotiff_plain_mode_returns_artifacts(tmp_path):
    """Plain path returns correct artifact metadata."""
    ds = _make_dataset()
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer.write(ds, task, task.grid_cells[0], {})

    assert set(result["variable"]) == {"B04", "B08"}
    assert bool(result["band"].isna().all())
    assert bool((result["cell_id"] == "test_cell").all())


# ---------------------------------------------------------------------------
# COG path
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not __import__("rasterio").__version__,
    reason="rasterio not available",
)
def test_write_geotiff_cog_mode_is_tiled(tmp_path):
    """COG path produces tiled output."""
    ds = _make_dataset()
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer.write(ds, task, task.grid_cells[0], {"cog": True})

    assert len(result) == 2
    for _, row in result.iterrows():
        import rasterio

        with rasterio.open(row["path"]) as src:
            block_height: int = src.block_shapes[0][0]
            assert block_height > 1


def test_write_geotiff_cog_mode_tiled(tmp_path):
    """COG output is tiled."""
    ds = _make_dataset(shape=(64, 64))
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer.write(ds, task, task.grid_cells[0], {"cog": True, "blocksize": 32})

    import rasterio

    for _, row in result.iterrows():
        with rasterio.open(row["path"]) as src:
            assert src.is_tiled
            assert src.block_shapes[0][0] == 32
            assert src.block_shapes[0][1] == 32


def test_write_geotiff_cog_mode_overviews(tmp_path):
    """COG output contains internal overviews."""
    ds = _make_dataset(shape=(64, 64))
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer.write(ds, task, task.grid_cells[0], {"cog": True})

    import rasterio

    for _, row in result.iterrows():
        with rasterio.open(row["path"]) as src:
            assert len(src.overviews(1)) > 0


def test_write_geotiff_cog_mode_overview_levels_explicit(tmp_path):
    """Custom overview_levels are honoured."""
    ds = _make_dataset(shape=(64, 64))
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer.write(
        ds,
        task,
        task.grid_cells[0],
        {"cog": True, "overview_levels": [2, 4]},
    )

    import rasterio

    for _, row in result.iterrows():
        with rasterio.open(row["path"]) as src:
            assert src.overviews(1) == [2, 4]


def test_write_geotiff_cog_mode_overview_resampling(tmp_path):
    """Overview resampling method is forwarded."""
    ds = _make_dataset(shape=(64, 64))
    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer.write(
        ds,
        task,
        task.grid_cells[0],
        {"cog": True, "overview_resampling": "bilinear"},
    )

    import rasterio

    for _, row in result.iterrows():
        with rasterio.open(row["path"]) as src:
            assert src.tags(ns="rio_overview")["resampling"] == "bilinear"


# ---------------------------------------------------------------------------
# Multi-band variables
# ---------------------------------------------------------------------------


def test_write_geotiff_multiband_plain(tmp_path):
    """Multi-band variables are split per band in plain mode."""
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

    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer.write(ds, task, task.grid_cells[0], {})

    assert len(result) == 3
    assert set(result["band"]) == {0, 1, 2}
    assert all(v == "RGB" for v in result["variable"])


def test_write_geotiff_multiband_cog(tmp_path):
    """Multi-band variables are split per band in COG mode."""
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

    task = _make_task(tmp_path)
    writer = WriteGeoTIFF()
    result = writer.write(ds, task, task.grid_cells[0], {"cog": True})

    import rasterio

    assert len(result) == 3
    for _, row in result.iterrows():
        with rasterio.open(row["path"]) as src:
            block_height: int = src.block_shapes[0][0]
            assert block_height > 1
            assert len(src.overviews(1)) > 0


# ---------------------------------------------------------------------------
# Optional params metadata
# ---------------------------------------------------------------------------


def test_write_geotiff_optional_params_registered():
    """COG-related params appear in optional_params."""
    writer = WriteGeoTIFF()
    names = {p.name for p in writer.optional_params}
    assert "cog" in names
    assert "blocksize" in names
    assert "overview_resampling" in names
    assert "overview_levels" in names
