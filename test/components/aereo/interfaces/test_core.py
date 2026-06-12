from typing import cast

import geopandas as gpd
import pytest
from aereo.interfaces import (
    ExtractionTask,
    GridConfig,
    PatchConfig,
)
from aereo.interfaces.utils import (
    infer_dataset_time_bounds,
    normalize_geometry_input,
    set_dataset_time_bounds,
    validate_aereo_dataset,
)
from pandera.typing.geopandas import GeoDataFrame
from pydantic import ValidationError
from shapely.geometry import Polygon


def test_extraction_task_validation():
    from aereo.interfaces.core import ExtractConfig
    from aereo.builtins.read import ReadODCSTAC

    df = gpd.GeoDataFrame(
        {"collection": ["GOES"], "start_time": ["2023-01-01"]},
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
    )
    grid_config = GridConfig(target_grid_dist=10_000)
    patch_config = PatchConfig(resolution=10.0)
    task = ExtractionTask(
        assets=cast(GeoDataFrame, df),
        extract=ExtractConfig(read=ReadODCSTAC()),
        output_uri="test",
        patches=[],
        grid_config=grid_config,
        patch_config=patch_config,
    )
    assert task.output_uri == "test"
    assert task.extract.read is not None


def test_grid_config_defaults_require_explicit_dist():
    gc = GridConfig(target_grid_dist=50_000)
    assert gc.target_grid_dist == 50_000
    assert gc.target_grid_overlap is False
    assert gc.grid_filter_mode == "intersection"


def test_grid_config_literal_validation():
    with pytest.raises(ValidationError):
        GridConfig(grid_filter_mode="invalid")  # type: ignore[arg-type]


def test_grid_config_from_yaml_string():
    yaml_text = """
    target_grid_dist: 100000
    target_grid_overlap: true
    """
    gc = GridConfig.from_yaml_string(yaml_text)
    assert gc.target_grid_dist == 100_000
    assert gc.target_grid_overlap is True


def test_grid_config_is_frozen():
    gc = GridConfig(target_grid_dist=50_000)
    with pytest.raises(ValidationError):
        gc.target_grid_dist = 100_000  # type: ignore[misc]


def test_grid_config_forbids_extra_fields():
    with pytest.raises(ValidationError):
        GridConfig(target_grid_dist=50_000, unknown_field=42)  # type: ignore[call-arg]


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


def test_batch_writer_is_aereo_plugin():
    from aereo.interfaces.core import BatchWriter, AereoPlugin

    assert issubclass(BatchWriter, AereoPlugin)


def test_extract_config_accepts_batch_writer():
    from aereo.interfaces.core import ExtractConfig, BatchWriter
    from aereo.builtins.read import ReadODCSTAC

    class _DummyBatchWriter(BatchWriter):
        def __call__(self, patches, task):
            from aereo.schemas import ArtifactSchema

            return ArtifactSchema.empty_geodataframe()

    cfg = ExtractConfig(
        read=ReadODCSTAC(),
        reproject=None,
        write=_DummyBatchWriter(),
    )
    assert isinstance(cfg.write, BatchWriter)
