"""Tests for the ReadODCSTAC built-in reader."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import box

from aereo.builtins import ReadODCSTAC
from aereo.grid import ExtractionPatch
from aereo.interfaces.core import ExtractionTask, GridConfig, PatchConfig
from aereo.pipeline import ExtractionJob
from aereo.schemas.core import AssetSchema
from pandera.typing.geopandas import GeoDataFrame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stac_item_dict(item_id: str = "item-001") -> dict[str, Any]:
    """Return a minimal serialised pystac.Item dictionary."""
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": [],
        "id": item_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-70.5, -33.5],
                    [-70.0, -33.5],
                    [-70.0, -33.0],
                    [-70.5, -33.0],
                    [-70.5, -33.5],
                ]
            ],
        },
        "bbox": [-70.5, -33.5, -70.0, -33.0],
        "properties": {
            "datetime": "2026-01-01T12:00:00Z",
        },
        "links": [],
        "assets": {
            "B04": {"href": "https://example.com/B04.tif", "type": "image/tiff"},
            "B08": {"href": "https://example.com/B08.tif", "type": "image/tiff"},
        },
        "collection": "sentinel-2-l2a",
    }


def _make_task(stac_item_dict: dict[str, Any] | None = None, aoi=None):
    """Return a minimal ExtractionTask with optional stac_item column."""
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = box(-70.5, -33.5, -70.0, -33.0)
    valid_df["collection"] = "sentinel-2-l2a"
    valid_df["channel_id"] = "B04"
    valid_df["start_time"] = pd.Timestamp("2026-01-01T12:00:00")
    valid_df["end_time"] = pd.Timestamp("2026-01-01T12:10:00")
    if stac_item_dict is not None:
        valid_df["stac_item"] = [stac_item_dict]

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
    from aereo.interfaces.core import ExtractConfig
    from aereo.builtins.read import ReadODCSTAC

    job = ExtractionJob(
        grid_config=grid_config,
        patch_config=patch_config,
        output_uri="/tmp/test",
        search=None,
        extract=ExtractConfig(read=ReadODCSTAC()),
        target_aoi=aoi,
    )
    return ExtractionTask(
        assets=GeoDataFrame(valid_df),
        job=job,
        patches=[patch],
        aoi=aoi,
    )


def _make_fake_ds() -> xr.Dataset:
    """Return a fake xr.Dataset simulating odc.stac.load output."""
    times = [datetime(2026, 1, 1, 12, 0, 0)]
    ds = xr.Dataset(
        {
            "B04": (["time", "y", "x"], np.ones((1, 4, 4), dtype=np.float32)),
            "B08": (["time", "y", "x"], np.ones((1, 4, 4), dtype=np.float32) * 0.8),
        },
        coords={
            "time": times,
            "y": range(4),
            "x": range(4),
        },
    )
    return ds


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_read_odcstac_fields():
    """ReadODCSTAC exposes the odc_params Pydantic field."""
    assert "odc_params" in ReadODCSTAC.model_fields


def test_read_odcstac_raises_without_stac_item_column():
    """__call__() raises ValueError when stac_item column is absent."""
    task = _make_task(stac_item_dict=None)
    reader = ReadODCSTAC()
    with pytest.raises(ValueError, match="stac_item"):
        reader(task)


def test_read_odcstac_raises_with_all_none_stac_items():
    """__call__() raises ValueError when all stac_item values are None."""
    task = _make_task(stac_item_dict=None)
    task.assets["stac_item"] = [None]
    reader = ReadODCSTAC()
    with pytest.raises(ValueError, match="No valid STAC items"):
        reader(task)


def test_read_odcstac_calls_odc_load_with_bbox(monkeypatch):
    """__call__() auto-injects bbox from grid cells and passes it to odc.stac.load."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["items"] = items
        captured["kwargs"] = kwargs
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    task = _make_task(_make_stac_item_dict())
    reader = ReadODCSTAC()
    result = reader(task)

    assert "bbox" in captured["kwargs"]
    assert captured["kwargs"]["bands"] == ["B04"]
    assert result is fake_ds


def test_read_odcstac_explicit_bands_override(monkeypatch):
    """odc_params bands override profile-derived bands."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["kwargs"] = kwargs
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    task = _make_task(_make_stac_item_dict())
    reader = ReadODCSTAC(odc_params={"bands": ["B04", "B08"]})
    reader(task)
    assert captured["kwargs"]["bands"] == ["B04", "B08"]


def test_read_odcstac_explicit_bbox_not_overridden(monkeypatch):
    """User-provided bbox in odc_params is not overridden by grid cells."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["kwargs"] = kwargs
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    custom_bbox = (-71.0, -34.0, -69.0, -32.0)
    task = _make_task(_make_stac_item_dict())
    reader = ReadODCSTAC(odc_params={"bbox": custom_bbox})
    reader(task)
    assert captured["kwargs"]["bbox"] == custom_bbox


def test_read_odcstac_deduplicates_items(monkeypatch):
    """Duplicate STAC item dicts (same id) are deduplicated before load."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["items"] = items
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    item_dict = _make_stac_item_dict("dup-id")

    # Build a two-row asset DataFrame manually.
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    for i in range(2):
        valid_df.loc[i] = {
            col: "test" for col in AssetSchema.to_schema().columns.keys()
        }
    valid_df["geometry"] = box(-70.5, -33.5, -70.0, -33.0)
    valid_df["collection"] = "sentinel-2-l2a"
    valid_df["channel_id"] = "B04"
    valid_df["start_time"] = pd.Timestamp("2026-01-01T12:00:00")
    valid_df["end_time"] = pd.Timestamp("2026-01-01T12:10:00")
    valid_df["stac_item"] = [item_dict, item_dict]

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
    from aereo.interfaces.core import ExtractConfig
    from aereo.builtins.read import ReadODCSTAC

    job = ExtractionJob(
        grid_config=grid_config,
        patch_config=patch_config,
        output_uri="/tmp/test",
        search=None,
        extract=ExtractConfig(read=ReadODCSTAC()),
    )
    task = ExtractionTask(
        assets=GeoDataFrame(valid_df),
        job=job,
        patches=[patch],
    )

    reader = ReadODCSTAC()
    reader(task)

    assert len(captured["items"]) == 1


def test_read_odcstac_infers_time_bounds(monkeypatch):
    """__call__() tags ds.attrs with start_time and end_time."""
    fake_ds = _make_fake_ds()

    def fake_odc_load(items, **kwargs):
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    task = _make_task(_make_stac_item_dict())
    reader = ReadODCSTAC()
    result = reader(task)

    assert "start_time" in result.attrs
    assert "end_time" in result.attrs
    assert result.attrs["start_time"] == datetime(2026, 1, 1, 12, 0, 0)


def test_read_odcstac_forwards_odc_params(monkeypatch):
    """odc_params are merged verbatim into odc.stac.load kwargs."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["kwargs"] = kwargs
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    task = _make_task(_make_stac_item_dict())
    reader = ReadODCSTAC(
        odc_params={
            "resampling": "bilinear",
            "groupby": "solar_day",
            "chunks": {"x": 1024, "y": 1024},
        }
    )
    reader(task)

    assert captured["kwargs"]["resampling"] == "bilinear"
    assert captured["kwargs"]["groupby"] == "solar_day"
    assert captured["kwargs"]["chunks"] == {"x": 1024, "y": 1024}
