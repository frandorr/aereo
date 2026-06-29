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
    )
    task = ExtractionTask(
        assets=cast(GeoDataFrame, df),
        job=job,
        patches=[],
    )
    assert task.output_uri == "test"
    assert task.read is not None


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
    )

    with pytest.raises(ValueError, match="share the same native CRS"):
        ExtractionTask(
            assets=cast(GeoDataFrame, df),
            job=job,
            patches=[],
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
    )

    task = ExtractionTask(
        assets=cast(GeoDataFrame, df),
        job=job,
        patches=[],
    )
    assert task is not None


def test_grid_dist_is_int():
    job = ExtractionJob(
        grid_dist=50_000,
        output_uri="test",
        read=read_odc_stac,
    )
    assert job.grid_dist == 50_000
    assert isinstance(job.grid_dist, int)


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
