from typing import cast

import geopandas as gpd
import pytest
from aereo.builtins.read import read_odc_stac
from aereo.interfaces import ExtractionTask
from aereo.pipeline import ExtractionJob
from aereo.interfaces.utils import (
    infer_dataset_time_bounds,
    normalize_geometry_input,
    set_dataset_time_bounds,
    validate_aereo_dataset,
)
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


def _dummy_writer(ds, path, **kwargs):
    return str(path)


def test_extraction_task_validation():
    df = gpd.GeoDataFrame(
        {"collection": ["GOES"], "start_time": ["2023-01-01"]},
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
    )
    grid_dist = 10_000
    job = ExtractionJob(
        grid_dist=grid_dist,
        output_uri="test",
        read=read_odc_stac,
        write=_dummy_writer,
    )
    task = ExtractionTask(
        id="task-1",
        assets=cast(GeoDataFrame, df),
        job=job,
    )
    assert task.output_uri == "test"
    assert task.read is not None
    assert task.write is not None


def test_extraction_task_rejects_mixed_crs():
    df = gpd.GeoDataFrame(
        {
            "collection": ["S2", "S2"],
            "start_time": ["2023-01-01", "2023-01-01"],
            "crs": ["EPSG:32631", "EPSG:32632"],
        },
        geometry=[
            Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
            Polygon([[2, 0], [3, 0], [3, 1], [2, 1]]),
        ],
    )
    grid_dist = 10_000
    job = ExtractionJob(
        grid_dist=grid_dist,
        output_uri="test",
        read=read_odc_stac,
        write=_dummy_writer,
    )

    with pytest.raises(ValueError, match="share the same native CRS"):
        ExtractionTask(
            id="task-mixed",
            assets=cast(GeoDataFrame, df),
            job=job,
        )


def test_extraction_task_accepts_single_crs():
    df = gpd.GeoDataFrame(
        {
            "collection": ["S2", "S2"],
            "start_time": ["2023-01-01", "2023-01-01"],
            "crs": ["EPSG:32631", "EPSG:32631"],
        },
        geometry=[
            Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
            Polygon([[2, 0], [3, 0], [3, 1], [2, 1]]),
        ],
    )
    grid_dist = 10_000
    job = ExtractionJob(
        grid_dist=grid_dist,
        output_uri="test",
        read=read_odc_stac,
        write=_dummy_writer,
    )

    task = ExtractionTask(
        id="task-single",
        assets=cast(GeoDataFrame, df),
        job=job,
    )
    assert task is not None


def test_grid_dist_is_int():
    job = ExtractionJob(
        grid_dist=50_000,
        output_uri="test",
        read=read_odc_stac,
        write=_dummy_writer,
    )
    assert job.grid_dist == 50_000
    assert isinstance(job.grid_dist, int)


# ---------------------------------------------------------------------------
# ExtractionTask read-oriented properties
# ---------------------------------------------------------------------------


def _make_task_with_assets(**asset_overrides):
    df = gpd.GeoDataFrame(
        {
            "id": ["asset-1"],
            "collection": ["C1"],
            "start_time": ["2023-01-01"],
            "end_time": ["2023-01-02"],
            "href": ["s3://bucket/file.tif"],
            **asset_overrides,
        },
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
    )
    job = ExtractionJob(
        grid_dist=10_000,
        output_uri="test",
        read=read_odc_stac,
        write=_dummy_writer,
    )
    return ExtractionTask(
        id="task-1",
        assets=cast(GeoDataFrame, df),
        job=job,
    )


def test_task_uris_returns_hrefs():
    task = _make_task_with_assets()
    assert task.uris == ["s3://bucket/file.tif"]


def test_task_bbox_prefers_task_aoi():
    from shapely.geometry import box

    task = _make_task_with_assets()
    task = ExtractionTask(
        id=task.id,
        assets=task.assets,
        job=task.job,
        aoi=box(0, 1, 2, 3),
    )
    assert task.bbox == (0.0, 1.0, 2.0, 3.0)


def test_task_bbox_falls_back_to_job_target_aoi():
    from shapely.geometry import box

    job = ExtractionJob(
        grid_dist=10_000,
        output_uri="test",
        read=read_odc_stac,
        write=_dummy_writer,
        target_aoi=box(10, 11, 12, 13),
    )
    task = ExtractionTask(
        id="task-1",
        assets=_make_task_with_assets().assets,
        job=job,
    )
    assert task.bbox == (10.0, 11.0, 12.0, 13.0)


def test_task_bbox_returns_none_without_aoi():
    task = _make_task_with_assets()
    assert task.bbox is None


def test_task_collections_returns_unique_sorted_collections():
    task = _make_task_with_assets()
    assert task.collections == ["C1"]


def test_task_datetime_range_derived_from_assets():
    from datetime import datetime

    task = _make_task_with_assets()
    datetime_range = task.datetime_range
    assert datetime_range is not None
    start, end = datetime_range
    assert start == datetime(2023, 1, 1)
    assert end == datetime(2023, 1, 2)


def test_task_stac_items_reconstructs_unique_items():
    item_dict = {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": [],
        "id": "item-001",
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
        "properties": {"datetime": "2026-01-01T12:00:00Z"},
        "links": [],
        "assets": {},
        "collection": "sentinel-2-l2a",
    }
    task = _make_task_with_assets(stac_item=[item_dict])
    items = task.stac_items
    assert len(items) == 1
    assert items[0].id == "item-001"


def test_task_stac_items_empty_when_column_missing():
    task = _make_task_with_assets()
    assert task.stac_items == []


# ---------------------------------------------------------------------------
# normalize_geometry_input
# ---------------------------------------------------------------------------


def test_normalize_geometry_input_passes_through_base_geometry():
    geom = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    assert normalize_geometry_input(geom) is geom


def test_normalize_geometry_input_accepts_geojson_dict():
    geojson = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
    }
    geom = normalize_geometry_input(geojson)
    assert isinstance(geom, Polygon)
    assert geom.is_valid


def test_normalize_geometry_input_accepts_geojson_path(tmp_path):
    geojson_path = tmp_path / "aoi.geojson"
    geojson_path.write_text(
        '{"type": "Feature", "geometry": {"type": "Polygon", '
        '"coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}, '
        '"properties": {}}'
    )
    geom = normalize_geometry_input(str(geojson_path))
    assert isinstance(geom, Polygon)
    assert geom.is_valid


def test_normalize_geometry_input_returns_none_for_none():
    assert normalize_geometry_input(None) is None


def test_normalize_geometry_input_rejects_unknown_type():
    with pytest.raises(ValueError, match="Invalid geometry input type"):
        normalize_geometry_input(12345)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_aereo_dataset
# ---------------------------------------------------------------------------


def test_validate_aereo_dataset_accepts_valid():
    import numpy as np
    import xarray as xr

    ds = xr.Dataset(
        {"B04": (["band", "y", "x"], np.ones((1, 4, 4)))},
        coords={"band": [1], "y": range(4), "x": range(4)},
    )
    # rioxarray crs is None by default, so we set require_crs=False
    validate_aereo_dataset(ds, require_crs=False)


def test_validate_aereo_dataset_rejects_non_dataset():
    with pytest.raises(ValueError, match="Expected xarray.Dataset"):
        validate_aereo_dataset("not a dataset", require_crs=False)


def test_validate_aereo_dataset_checks_required_dims():
    import numpy as np
    import xarray as xr

    ds = xr.Dataset(
        {"B04": (["y", "x"], np.ones((4, 4)))},
        coords={"y": range(4), "x": range(4)},
    )
    validate_aereo_dataset(ds, require_crs=False, require_dims=["y", "x"])

    with pytest.raises(ValueError, match="missing required dimensions"):
        validate_aereo_dataset(ds, require_crs=False, require_dims=["time"])


def test_validate_aereo_dataset_checks_crs_when_required():
    import numpy as np
    import xarray as xr

    ds = xr.Dataset(
        {"B04": (["band", "y", "x"], np.ones((1, 4, 4)))},
        coords={"band": [1], "y": range(4), "x": range(4)},
    )
    # Without rioxarray crs, require_crs=True should fail
    with pytest.raises(ValueError, match="must have a CRS"):
        validate_aereo_dataset(ds, require_crs=True)


def test_set_dataset_time_bounds():
    import xarray as xr
    from datetime import datetime

    ds = xr.Dataset()
    t1 = datetime(2026, 1, 1, 12, 0, 0)
    t2 = datetime(2026, 1, 1, 12, 10, 0)
    ds = set_dataset_time_bounds(ds, t1, t2)

    assert ds.attrs["start_time"] == t1
    assert ds.attrs["end_time"] == t2


def test_infer_dataset_time_bounds():
    import numpy as np
    import xarray as xr
    from datetime import datetime

    t1 = datetime(2026, 1, 1, 12, 0, 0)
    t2 = datetime(2026, 1, 1, 12, 10, 0)
    ds = xr.Dataset(
        {"B04": (["time", "y", "x"], np.ones((2, 4, 4)))},
        coords={
            "time": [t1, t2],
            "y": range(4),
            "x": range(4),
        },
    )

    ds = infer_dataset_time_bounds(ds)
    assert ds.attrs["start_time"] == t1
    assert ds.attrs["end_time"] == t2


def test_task_staging_protocol_removed():
    """TaskStaging protocol was removed from the public interfaces module."""
    import importlib

    module = importlib.import_module("aereo.interfaces")
    assert not hasattr(module, "TaskStaging")
