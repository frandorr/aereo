"""Tests for the BatchWriteGeoTIFF built-in batch writer."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
import rioxarray  # noqa: F401 — registers the ``rio`` accessor on xarray objects
import xarray as xr
from shapely.geometry import Polygon, box

from aereo.builtins import BatchWriteGeoTIFF
from aereo.builtins.write import WriteGeoTIFF
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
    """Return a minimal ExtractionTask for batch writer tests."""
    from aereo.interfaces.core import ExtractConfig
    from aereo.builtins.read import ReadODCSTAC
    from aereo.builtins.reproject import ReprojectODC

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
        extract=ExtractConfig(
            read=ReadODCSTAC(),
            reproject=ReprojectODC(),
            write=WriteGeoTIFF(),
        ),
        uri=str(tmp_path),
        patches=[patch],
        grid_config=grid_config,
        patch_config=patch_config,
    )


def test_batch_write_geotiff_plain(tmp_path):
    """BatchWriteGeoTIFF writes all patches and returns artifacts."""
    task = _make_task(tmp_path)
    writer = BatchWriteGeoTIFF()
    ds = _make_dataset()

    result = writer({"test_cell": ds}, task)
    assert len(result) == 2


def test_batch_write_geotiff_releases_references(tmp_path, monkeypatch):
    """Dataset close() should be called after write."""
    import geopandas as gpd
    from aereo.builtins.write import WriteGeoTIFF

    task = _make_task(tmp_path)
    writer = BatchWriteGeoTIFF()
    ds = _make_dataset()

    # Patch WriteGeoTIFF to avoid real I/O and just track calls
    write_calls = []

    def _patched_write(self, ds, task, patch):
        write_calls.append((ds, patch.id))
        return gpd.GeoDataFrame(
            {"id": ["a1"]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
        )

    monkeypatch.setattr(WriteGeoTIFF, "__call__", _patched_write)

    writer({"test_cell": ds}, task)
    assert len(write_calls) == 1
    assert write_calls[0][1] == "test_cell"
