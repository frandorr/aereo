"""Tests for the built-in write pipeline module."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rioxarray  # noqa: F401
import xarray as xr
from hamilton import driver
from shapely.geometry import Polygon, box

from aereo.interfaces import PipelineProfile
from aereo.write import core as write_module
from aereo.write.core import (
    _derive_collection,
    _derive_source_ids,
    _derive_temporal_bounds,
    _stack_dataset,
    supported_collections,
    write_cogs,
)


# ---------------------------------------------------------------------------
# supported_collections
# ---------------------------------------------------------------------------


def test_supported_collections_is_wildcard() -> None:
    """The write module supports any collection."""
    assert supported_collections == ("*",)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_stack_dataset_concatenates_vars() -> None:
    """_stack_dataset stacks multiple data variables along band dim."""
    da1 = xr.DataArray(np.zeros((2, 2)), dims=("y", "x"), name="var1")
    da2 = xr.DataArray(np.ones((2, 2)), dims=("y", "x"), name="var2")
    ds = xr.Dataset({"var1": da1, "var2": da2})

    stacked = _stack_dataset(ds)
    assert "band" in stacked.dims
    assert stacked.sizes["band"] == 2


def test_derive_temporal_bounds_from_assets() -> None:
    """_derive_temporal_bounds reads start/end from task.assets."""
    task = MagicMock()
    task.assets = pd.DataFrame(
        {
            "start_time": pd.to_datetime(["2024-01-01 10:00:00"]),
            "end_time": pd.to_datetime(["2024-01-01 11:00:00"]),
        }
    )
    start, end = _derive_temporal_bounds(task)
    assert start == pd.Timestamp("2024-01-01 10:00:00")
    assert end == pd.Timestamp("2024-01-01 11:00:00")


def test_derive_temporal_bounds_empty_assets() -> None:
    """Empty assets yield None for both bounds."""
    task = MagicMock()
    task.assets = pd.DataFrame()
    start, end = _derive_temporal_bounds(task)
    assert start is None
    assert end is None


def test_derive_source_ids_from_assets() -> None:
    """_derive_source_ids joins unique asset ids."""
    task = MagicMock()
    task.assets = pd.DataFrame({"id": ["a", "b", "a"]})
    assert _derive_source_ids(task) == "a,b"


def test_derive_collection_from_profile() -> None:
    """_derive_collection prefers profile.collections."""
    task = MagicMock()
    task.profile = MagicMock()
    task.profile.collections = {"S2": ["B01"]}
    assert _derive_collection(task) == "S2"


def test_derive_collection_from_assets_fallback() -> None:
    """Falls back to task.assets collection column."""
    task = MagicMock()
    task.profile = MagicMock()
    task.profile.collections = {}
    task.assets = pd.DataFrame({"collection": ["LC08"]})
    assert _derive_collection(task) == "LC08"


# ---------------------------------------------------------------------------
# write_cogs
# ---------------------------------------------------------------------------


def _make_mock_task(
    tmp_path: Any,
    *,
    cells: list[Any] | None = None,
    profile: PipelineProfile | None = None,
    assets: pd.DataFrame | None = None,
) -> Any:
    """Build a minimal mock extraction task."""
    task = MagicMock()
    task.uri = str(tmp_path)
    task.grid_cells = cells or []

    if profile is None:
        profile = PipelineProfile(
            name="test_profile",
            resolution=10.0,
            collections={"S2": ["B01"]},
        )
    task.profile = profile

    if assets is None:
        assets = pd.DataFrame(
            {
                "id": ["scene-1"],
                "start_time": pd.to_datetime(["2024-01-01 10:00:00"]),
                "end_time": pd.to_datetime(["2024-01-01 11:00:00"]),
                "collection": ["S2"],
            }
        )
    task.assets = assets

    return task


def _make_test_dataset(
    *,
    n_vars: int = 1,
    crs: str = "EPSG:4326",
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
) -> xr.Dataset:
    """Create a small in-memory dataset with rioxarray metadata."""
    data_vars: dict[str, xr.DataArray] = {}
    for i in range(n_vars):
        da = xr.DataArray(
            np.zeros((2, 2), dtype=np.float32),
            dims=("y", "x"),
            coords={
                "y": [0.5, -0.5],
                "x": [0.5, 1.5],
            },
            name=f"var{i}",
        )
        da.rio.write_crs(crs, inplace=True)
        # Set spatial bounds so rioxarray can compute geometry.
        da.rio.write_transform(inplace=True)
        da.rio.update_encoding({"dtype": "float32"}, inplace=True)
        data_vars[f"var{i}"] = da

    ds = xr.Dataset(data_vars)
    return ds


def test_write_cogs_raises_on_none_dataset() -> None:
    """write_cogs rejects a None dataset."""
    task = MagicMock()
    task.uri = "/tmp"
    with pytest.raises(ValueError, match="received None dataset"):
        write_cogs(None, task)


def test_write_cogs_raises_on_missing_uri() -> None:
    """write_cogs rejects a task without uri."""
    task = MagicMock()
    task.uri = None
    ds = _make_test_dataset()
    with pytest.raises(ValueError, match="requires task.uri"):
        write_cogs(ds, task)


def test_write_cogs_single_cell(tmp_path: Any) -> None:
    """write_cogs produces a single EOIDS file for one cell."""
    cell = MagicMock()
    cell.id.return_value = "36D61L"
    cell.geom = box(0, 0, 1, 1)

    task = _make_mock_task(tmp_path, cells=[cell])
    ds = _make_test_dataset(n_vars=2)

    gdf = write_cogs(ds, task)

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 1
    assert gdf.iloc[0]["collection"] == "S2"
    assert gdf.iloc[0]["source_ids"] == "scene-1"
    assert (tmp_path / "loc-36D61L").exists()


def test_write_cogs_no_cells(tmp_path: Any) -> None:
    """write_cogs produces a file without cell directory when no cells."""
    task = _make_mock_task(tmp_path, cells=[])
    ds = _make_test_dataset(n_vars=1)

    gdf = write_cogs(ds, task)

    assert len(gdf) == 1
    assert "loc-" not in gdf.iloc[0]["uri"]


def test_write_cogs_multiple_cells(tmp_path: Any) -> None:
    """write_cogs produces one file per cell."""
    cell_a = MagicMock()
    cell_a.id.return_value = "A"
    cell_a.geom = box(0, 0, 1, 1)

    cell_b = MagicMock()
    cell_b.id.return_value = "B"
    cell_b.geom = box(2, 2, 3, 3)

    task = _make_mock_task(tmp_path, cells=[cell_a, cell_b])
    ds = _make_test_dataset(n_vars=1)

    gdf = write_cogs(ds, task)

    assert len(gdf) == 2
    assert any("loc-A" in row["uri"] for _, row in gdf.iterrows())
    assert any("loc-B" in row["uri"] for _, row in gdf.iterrows())


def test_write_cogs_empty_dataset_raises() -> None:
    """An empty xarray.Dataset raises ValueError."""
    task = MagicMock()
    task.uri = "/tmp"
    ds = xr.Dataset()
    with pytest.raises(ValueError, match="empty xarray.Dataset"):
        write_cogs(ds, task)


def test_write_cogs_forwards_compress_zlevel(tmp_path: Any) -> None:
    """write_cogs passes compress and zlevel to rio.to_raster."""
    cell = MagicMock()
    cell.id.return_value = "C"
    cell.geom = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])

    task = _make_mock_task(tmp_path, cells=[cell])
    ds = _make_test_dataset(n_vars=1)

    with patch("xarray.DataArray.rio.to_raster") as mock_to_raster:
        mock_to_raster.return_value = None
        write_cogs(ds, task, compress="lzw", zlevel=5)

        mock_to_raster.assert_called_once()
        _, kwargs = mock_to_raster.call_args
        assert kwargs["compress"] == "lzw"
        assert kwargs["zlevel"] == 5


# ---------------------------------------------------------------------------
# Hamilton integration
# ---------------------------------------------------------------------------


def test_write_pipeline_runs(tmp_path: Any) -> None:
    """write.py can be built into a Hamilton driver and executes write_cogs."""
    dr = driver.Builder().with_modules(write_module).build()

    cell = MagicMock()
    cell.id.return_value = "H"
    cell.geom = box(0, 0, 1, 1)

    task = _make_mock_task(tmp_path, cells=[cell])
    ds = _make_test_dataset(n_vars=1)

    result = dr.execute(
        ["write_cogs"],
        inputs={"ds": ds, "task": task, "compress": "deflate", "zlevel": 1},
    )
    assert "write_cogs" in result
    assert isinstance(result["write_cogs"], gpd.GeoDataFrame)
    assert len(result["write_cogs"]) == 1
