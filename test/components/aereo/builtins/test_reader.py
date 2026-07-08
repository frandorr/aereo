"""Tests for the read_odc_stac built-in reader."""

from __future__ import annotations

import attrs
from datetime import datetime
from functools import partial
from typing import Any, cast

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import box

from aereo.builtins import read_odc_stac
from aereo.interfaces.core import ExtractionTask
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


def _make_assets(
    stac_item_dict: dict[str, Any] | None = None,
) -> GeoDataFrame[AssetSchema]:
    """Return a minimal AssetSchema GeoDataFrame with optional stac_item column."""
    data: dict[str, Any] = {
        "id": ["asset-1"],
        "collection": ["sentinel-2-l2a"],
        "start_time": [pd.Timestamp("2026-01-01T12:00:00")],
        "end_time": [pd.Timestamp("2026-01-01T12:10:00")],
        "href": ["https://example.com/B04.tif"],
        "geometry": [box(-70.5, -33.5, -70.0, -33.0)],
        "channel_id": ["B04"],
    }
    if stac_item_dict is not None:
        data["stac_item"] = [stac_item_dict]

    return cast(
        GeoDataFrame[AssetSchema],
        gpd.GeoDataFrame(data, crs="EPSG:4326"),
    )


def _make_task(stac_item_dict: dict[str, Any] | None = None) -> ExtractionTask:
    """Return a minimal ExtractionTask with optional stac_item column."""
    assets = _make_assets(stac_item_dict)
    job = ExtractionJob(
        name="test-job",
        grid_dist=50_000,
        output_uri="/tmp/test",
        read=read_odc_stac,
        write=lambda ds, path, **kwargs: str(path),
    )
    return ExtractionTask(
        id="task-0",
        assets=assets,
        job=job,
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
    """read_odc_stac exposes task and **kwargs, not files/assets/aoi."""
    import inspect

    sig = inspect.signature(read_odc_stac)
    assert "task" in sig.parameters
    assert "kwargs" in sig.parameters
    assert "files" not in sig.parameters
    assert "assets" not in sig.parameters
    assert "aoi" not in sig.parameters


def test_read_odcstac_raises_without_stac_items():
    """__call__() raises ValueError when task.stac_items is empty."""
    task = _make_task(stac_item_dict=None)
    reader = read_odc_stac
    with pytest.raises(ValueError, match="STAC item"):
        reader(task)


def test_read_odcstac_raises_without_stac_item_column():
    """__call__() raises ValueError when task.stac_items is empty."""
    task = _make_task(stac_item_dict=None)
    reader = read_odc_stac
    with pytest.raises(ValueError, match="STAC item"):
        reader(task)


def test_read_odcstac_raises_with_all_none_stac_items():
    """__call__() raises ValueError when all stac_item values are None."""
    task = _make_task(stac_item_dict=None)
    task.assets["stac_item"] = [None]
    reader = read_odc_stac
    with pytest.raises(ValueError, match="STAC item"):
        reader(task)


def test_read_odcstac_forwards_bands(monkeypatch):
    """__call__() passes bands inferred from assets to odc.stac.load."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["items"] = items
        captured["kwargs"] = kwargs
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    task = _make_task(_make_stac_item_dict())
    reader = read_odc_stac
    result = reader(task)

    assert captured["kwargs"]["bands"] == ["B04"]
    assert isinstance(result, xr.Dataset)
    assert "time" not in result.dims


def test_read_odcstac_explicit_bands_override(monkeypatch):
    """Explicit bands override profile-derived bands."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["kwargs"] = kwargs
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    task = _make_task(_make_stac_item_dict())
    reader = partial(read_odc_stac, bands=["B04", "B08"])
    reader(task)
    assert captured["kwargs"]["bands"] == ["B04", "B08"]


def test_read_odcstac_explicit_bbox_not_overridden(monkeypatch):
    """User-provided bbox is preserved."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["kwargs"] = kwargs
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    custom_bbox = (-71.0, -34.0, -69.0, -32.0)
    task = _make_task(_make_stac_item_dict())
    reader = partial(read_odc_stac, bbox=custom_bbox)
    reader(task)
    assert captured["kwargs"]["bbox"] == custom_bbox


def test_read_odcstac_forwards_aoi_as_bbox(monkeypatch):
    """aoi is forwarded to odc.stac.load as bbox."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["kwargs"] = kwargs
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    aoi = (-70.5, -33.5, -70.0, -33.0)
    task = _make_task(_make_stac_item_dict())
    task = attrs.evolve(task, aoi=box(-70.5, -33.5, -70.0, -33.0))
    reader = read_odc_stac
    reader(task)

    assert captured["kwargs"]["bbox"] == aoi


def test_read_odcstac_aoi_overridden_by_user_bbox(monkeypatch):
    """User-provided bbox takes precedence over aoi."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["kwargs"] = kwargs
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    custom_bbox = (-71.0, -34.0, -69.0, -32.0)
    task = _make_task(_make_stac_item_dict())
    reader = partial(read_odc_stac, bbox=custom_bbox)
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

    assets = gpd.GeoDataFrame(
        {
            "id": ["asset-1", "asset-2"],
            "collection": ["sentinel-2-l2a", "sentinel-2-l2a"],
            "start_time": [pd.Timestamp("2026-01-01T12:00:00")] * 2,
            "end_time": [pd.Timestamp("2026-01-01T12:10:00")] * 2,
            "href": ["https://example.com/B04.tif", "https://example.com/B08.tif"],
            "geometry": [box(-70.5, -33.5, -70.0, -33.0)] * 2,
            "channel_id": ["B04", "B04"],
            "stac_item": [item_dict, item_dict],
        },
        crs="EPSG:4326",
    )

    from aereo.pipeline import ExtractionJob

    job = ExtractionJob(
        name="test-job",
        grid_dist=50_000,
        output_uri="/tmp/test",
        read=read_odc_stac,
        write=lambda ds, path, **kwargs: str(path),
    )
    task = ExtractionTask(
        id="task-0",
        assets=cast(GeoDataFrame[AssetSchema], assets),
        job=job,
    )
    reader = read_odc_stac
    reader(task)

    assert len(captured["items"]) == 1


def test_read_odcstac_infers_time_bounds(monkeypatch):
    """__call__() tags ds.attrs with start_time and end_time."""
    fake_ds = _make_fake_ds()

    def fake_odc_load(items, **kwargs):
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    task = _make_task(_make_stac_item_dict())
    reader = read_odc_stac
    result = reader(task)

    assert "start_time" in result.attrs
    assert "end_time" in result.attrs
    assert result.attrs["start_time"] == datetime(2026, 1, 1, 12, 0, 0)


def test_read_odcstac_forwards_kwargs(monkeypatch):
    """Extra keyword arguments are forwarded verbatim to odc.stac.load."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["kwargs"] = kwargs
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    task = _make_task(_make_stac_item_dict())
    reader = partial(
        read_odc_stac,
        resampling="bilinear",
        groupby="solar_day",
        chunks={"x": 1024, "y": 1024},
    )
    reader(task)

    assert captured["kwargs"]["resampling"] == "bilinear"
    assert captured["kwargs"]["groupby"] == "solar_day"
    assert captured["kwargs"]["chunks"] == {"x": 1024, "y": 1024}


def test_read_odcstac_handles_numpy_arrays_in_stac_item(monkeypatch):
    """Numpy arrays round-tripped through Parquet are normalised to Python lists."""
    fake_ds = _make_fake_ds()
    captured: dict[str, Any] = {}

    def fake_odc_load(items, **kwargs):
        captured["items"] = items
        return fake_ds

    monkeypatch.setattr("aereo.builtins.read.odc_load", fake_odc_load)

    item_dict = _make_stac_item_dict("np-item")
    # Simulate a Parquet round-trip that leaves list fields as ndarrays.
    item_dict["stac_extensions"] = np.array(["eo", "projection"])
    item_dict["bbox"] = np.array([-70.5, -33.5, -70.0, -33.0])
    item_dict["properties"]["numeric"] = np.int64(42)

    task = _make_task(item_dict)
    reader = read_odc_stac
    reader(task)

    assert len(captured["items"]) == 1
    assert captured["items"][0].id == "np-item"
