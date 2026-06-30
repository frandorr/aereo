from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from aereo.executors import LocalExecutor
from aereo.interfaces import (
    SearchProvider,
    TaskBuilder,
    empty_asset_result,
)
from aereo.interfaces.core import ExtractionTask, Reader
from aereo.pipeline import ExtractionJob
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


class FakeReader(Reader):
    """Minimal reader for testing ExtractionJob validation."""

    def __call__(self, files, assets=None, **kwargs):
        raise NotImplementedError


def test_job_no_search_or_task_builder():
    _ = ExtractionJob(
        grid_dist=1000,
        output_uri="/tmp/out",
        read=FakeReader(),
        write=_DummyWriter(),
    )
    assert "search" not in ExtractionJob.model_fields
    assert "task_builder" not in ExtractionJob.model_fields


def test_extraction_job_from_yaml_dict(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
name: s2_b04_over_my_aoi
grid_dist: 50000
output_uri: "out_dir"
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.name == "s2_b04_over_my_aoi"
    assert job.output_uri == "out_dir"
    assert job.grid_dist == 50000
    assert job.read is not None
    assert job.write is not None


def test_extraction_job_from_yaml_target(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
_target_: aereo.pipeline.ExtractionJob
grid_dist: 10000
output_uri: "out_dir"
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.output_uri == "out_dir"
    assert job.grid_dist == 10000
    assert job.read is not None


def test_extraction_job_from_yaml_invalid(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
grid_dist: not_an_int
output_uri: "out_dir"
read:
  _target_: aereo.builtins.read.read_odc_stac
"""
    )
    # Pydantic or Hydra will raise ValidationError or InstantiationException
    with pytest.raises(Exception):
        ExtractionJob.from_yaml(job_yaml)


def test_extraction_job_from_yaml_with_writer(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
grid_dist: 50000
output_uri: "out_dir"
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert callable(job.write)


def _sample_geojson() -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]
        ],
    }


def test_extraction_job_load_from_config_package(tmp_path: Path):
    config_dir = tmp_path / "conf"
    config_dir.mkdir()

    (config_dir / "main_config.yaml").write_text(
        """
defaults:
  - grid_dist@_global_: default
  - read@_global_: sentinel2
  - write@_global_: geotiff
  - _self_

output_uri: "out_dir"
target_aoi:
  type: Polygon
  coordinates:
    - [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]
"""
    )

    grid_dir = config_dir / "grid_dist"
    grid_dir.mkdir()
    (grid_dir / "default.yaml").write_text("grid_dist: 75000\n")

    read_dir = config_dir / "read"
    read_dir.mkdir()
    (read_dir / "sentinel2.yaml").write_text(
        "read:\n  _target_: aereo.builtins.read.read_odc_stac\n"
    )
    write_dir = config_dir / "write"
    write_dir.mkdir()
    (write_dir / "geotiff.yaml").write_text(
        "write:\n  _target_: aereo.builtins.write.write_geotiff\n"
    )

    job = ExtractionJob.load_from_config(config_dir)
    assert job.output_uri == "out_dir"
    assert job.grid_dist == 75_000
    assert isinstance(job.target_aoi, Polygon)


def test_extraction_job_load_from_config_package_with_override(tmp_path: Path):
    config_dir = tmp_path / "conf"
    config_dir.mkdir()

    (config_dir / "main_config.yaml").write_text(
        """
defaults:
  - read@_global_: sentinel2
  - write@_global_: geotiff
  - _self_

grid_dist: 50000
output_uri: "out_dir"
"""
    )

    read_dir = config_dir / "read"
    read_dir.mkdir()
    (read_dir / "sentinel2.yaml").write_text(
        "read:\n  _target_: aereo.builtins.read.read_odc_stac\n"
    )
    write_dir = config_dir / "write"
    write_dir.mkdir()
    (write_dir / "geotiff.yaml").write_text(
        "write:\n  _target_: aereo.builtins.write.write_geotiff\n"
    )

    job = ExtractionJob.load_from_config(config_dir)
    assert job.grid_dist == 50_000


def test_extraction_job_load_from_config_package_without_targets(tmp_path: Path):
    """Concrete Pydantic models do not need ``_target_`` in Hydra configs."""
    config_dir = tmp_path / "conf"
    config_dir.mkdir()

    (config_dir / "main_config.yaml").write_text(
        """
defaults:
  - grid_dist@_global_: default
  - read@_global_: sentinel2
  - write@_global_: geotiff
  - _self_

output_uri: "out_dir"
"""
    )

    grid_dir = config_dir / "grid_dist"
    grid_dir.mkdir()
    (grid_dir / "default.yaml").write_text("grid_dist: 75000\n")

    read_dir = config_dir / "read"
    read_dir.mkdir()
    (read_dir / "sentinel2.yaml").write_text(
        "read:\n  _target_: aereo.builtins.read.read_odc_stac\n"
    )
    write_dir = config_dir / "write"
    write_dir.mkdir()
    (write_dir / "geotiff.yaml").write_text(
        "write:\n  _target_: aereo.builtins.write.write_geotiff\n"
    )

    job = ExtractionJob.load_from_config(config_dir)
    assert isinstance(job.grid_dist, int)
    assert job.grid_dist == 75_000
    assert job.read is not None
    assert job.write is not None


def test_extraction_job_accepts_geojson_dict(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
grid_dist: 50000
output_uri: "out_dir"
target_aoi:
  type: Polygon
  coordinates:
    - [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert isinstance(job.target_aoi, Polygon)
    assert job.effective_target_aoi is job.target_aoi


def test_extraction_job_accepts_geojson_file_path(tmp_path: Path):
    aoi_file = tmp_path / "aoi.geojson"
    aoi_file.write_text(str(_sample_geojson()).replace("'", '"'))

    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        f"""
grid_dist: 50000
output_uri: "out_dir"
target_aoi: {aoi_file}
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert isinstance(job.target_aoi, Polygon)


def test_extraction_job_target_aoi_defaults_to_none(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
grid_dist: 50000
output_uri: "out_dir"
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.target_aoi is None
    assert job.effective_target_aoi is None


# ---------------------------------------------------------------------------
# Orchestration methods
# ---------------------------------------------------------------------------


class _DummyReader(Reader):
    def __call__(self, files: list[str], assets=None, **kwargs) -> xr.Dataset:
        return xr.Dataset(
            {"B04": (["y", "x"], np.ones((4, 4)))},
            coords={"y": range(4), "x": range(4)},
        )


class _DummyWriter:
    def __call__(self, ds: xr.Dataset, path: str, **kwargs) -> str:
        import numpy as np
        import rioxarray  # noqa: F401

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        da = xr.DataArray(
            np.ones((4, 4), dtype=np.float32),
            dims=["y", "x"],
            coords={"y": range(4), "x": range(4)},
        )
        da.rio.write_crs("EPSG:4326", inplace=True)
        da.rio.to_raster(path)
        return path


def _make_assets() -> GeoDataFrame[AssetSchema]:
    """Return a minimal non-empty AssetSchema GeoDataFrame."""
    df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    df["geometry"] = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    df["collection"] = "C1"
    df["start_time"] = pd.Timestamp("2023-01-01")
    df["end_time"] = pd.Timestamp("2023-01-02")
    return cast(GeoDataFrame[AssetSchema], df)


def _make_task(job: ExtractionJob, task_id: str = "task-1") -> ExtractionTask:
    """Return a minimal ExtractionTask tied to *job*."""
    valid_df = gpd.GeoDataFrame(
        {
            "id": ["asset-1"],
            "collection": ["C1"],
            "start_time": [pd.Timestamp("2023-01-01")],
            "end_time": [pd.Timestamp("2023-01-02")],
            "href": ["s3://bucket/file.tif"],
            "geometry": [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
        },
        crs="EPSG:4326",
    )

    return ExtractionTask(
        id=task_id,
        assets=cast(GeoDataFrame[AssetSchema], valid_df),
        job=job,
    )


def test_job_search_calls_provider():
    job = ExtractionJob(
        grid_dist=1000,
        output_uri="/tmp/out",
        read=FakeReader(),
        write=_DummyWriter(),
    )
    provider = MagicMock(spec=SearchProvider)
    provider.return_value = empty_asset_result()
    assets = job.search(provider)
    provider.assert_called_once()
    assert isinstance(assets, gpd.GeoDataFrame)


def test_job_search_passes_aoi_to_provider():
    aoi = Polygon([[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]])
    job = ExtractionJob(
        grid_dist=1000,
        output_uri="/tmp/out",
        read=FakeReader(),
        write=_DummyWriter(),
        target_aoi=aoi,
    )
    provider = MagicMock(spec=SearchProvider)
    provider.return_value = empty_asset_result()
    job.search(provider)
    provider.assert_called_once_with(intersects=aoi)


def test_job_search_aoi_argument_overrides_target_aoi():
    target_aoi = Polygon([[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]])
    search_aoi = Polygon([[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])
    job = ExtractionJob(
        grid_dist=1000,
        output_uri="/tmp/out",
        read=FakeReader(),
        write=_DummyWriter(),
        target_aoi=target_aoi,
    )
    provider = MagicMock(spec=SearchProvider)
    provider.return_value = empty_asset_result()
    job.search(provider, aoi=search_aoi)
    provider.assert_called_once_with(intersects=search_aoi)


def test_job_build_tasks_calls_task_builder():
    job = ExtractionJob(
        grid_dist=1000,
        output_uri="/tmp/out",
        read=FakeReader(),
        write=_DummyWriter(),
    )
    builder = MagicMock(spec=TaskBuilder)
    builder.return_value = []
    tasks = job.build_tasks(_make_assets(), builder)
    builder.assert_called_once()
    assert tasks == []


def test_job_build_tasks_passes_builder_kwargs():
    job = ExtractionJob(
        grid_dist=1000,
        output_uri="/tmp/out",
        read=FakeReader(),
        write=_DummyWriter(),
    )
    builder = MagicMock(spec=TaskBuilder)
    builder.return_value = []
    assets = _make_assets()
    job.build_tasks(
        assets,
        builder,
        cells_per_task=20,
    )
    builder.assert_called_once()
    call_args = builder.call_args
    assert call_args.args[0] is assets
    assert call_args.args[1] is job
    assert call_args.kwargs["cells_per_task"] == 20


def test_job_build_tasks_returns_empty_for_empty_assets():
    job = ExtractionJob(
        grid_dist=1000,
        output_uri="/tmp/out",
        read=FakeReader(),
        write=_DummyWriter(),
    )
    builder = MagicMock(spec=TaskBuilder)
    empty_assets = gpd.GeoDataFrame(
        columns=list(AssetSchema.to_schema().columns.keys()),
        geometry="geometry",
    )
    tasks = job.build_tasks(cast(GeoDataFrame[AssetSchema], empty_assets), builder)
    builder.assert_not_called()
    assert tasks == []


def test_job_execute_uses_default_executor(tmp_path: Path):
    job = ExtractionJob(
        grid_dist=1000,
        resolution=10.0,
        output_uri=str(tmp_path / "out"),
        read=_DummyReader(),
        write=_DummyWriter(),
    )
    tasks = [_make_task(job)]
    artifacts = job.execute(tasks)
    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) >= 1


def test_job_execute_with_custom_executor(tmp_path: Path):
    job = ExtractionJob(
        grid_dist=1000,
        resolution=10.0,
        output_uri=str(tmp_path / "out"),
        read=_DummyReader(),
        write=_DummyWriter(),
    )
    custom = LocalExecutor(workers=2, use_threads=True)
    tasks = [_make_task(job, task_id="a"), _make_task(job, task_id="b")]
    artifacts = job.execute(tasks, executor=custom)
    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) >= 2


def test_job_execute_empty_tasks_returns_empty_catalog():
    job = ExtractionJob(
        grid_dist=1000,
        output_uri="/tmp/out",
        read=FakeReader(),
        write=_DummyWriter(),
    )
    artifacts = job.execute([])
    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) == 0


def test_job_write_catalog(tmp_path: Path):
    job = ExtractionJob(
        grid_dist=1000,
        output_uri=str(tmp_path / "out"),
        read=FakeReader(),
        write=_DummyWriter(),
    )
    artifacts = cast(
        GeoDataFrame[ArtifactSchema],
        gpd.GeoDataFrame(
            {"id": ["a1"]},
            geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
        ),
    )
    uri = job.write_catalog(artifacts)
    assert uri == str(tmp_path / "out" / "artifacts.parquet")
    assert Path(uri).exists()


def test_load_plugin_helper(tmp_path: Path):
    """load_plugin returns a partial function from a Hydra config group file."""
    from aereo.pipeline import load_plugin

    search_yaml = tmp_path / "search" / "dummy.yaml"
    search_yaml.parent.mkdir(parents=True)
    search_yaml.write_text(
        """
_target_: aereo.builtins.search.search_stac
stac_api_url: "https://example.com/stac"
collections:
  s2: ["red"]
"""
    )

    provider = load_plugin(tmp_path, "search", "dummy")
    assert callable(provider)
    # Bound config values should be present on the partial.
    assert provider.keywords["stac_api_url"] == "https://example.com/stac"

    task_builder_yaml = tmp_path / "task_builder" / "grouped.yaml"
    task_builder_yaml.parent.mkdir(parents=True)
    task_builder_yaml.write_text(
        """
_target_: aereo.builtins.task_builder.build_grouped_tasks
cells_per_task: 7
"""
    )

    task_builder = load_plugin(tmp_path, "task_builder", "grouped")
    assert callable(task_builder)
    assert task_builder.keywords["cells_per_task"] == 7
