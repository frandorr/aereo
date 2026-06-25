from pathlib import Path

import pytest
from aereo.interfaces import ExtractConfig, GridConfig, PatchConfig
from aereo.interfaces.core import Reader
from aereo.pipeline import ExtractionJob
from shapely.geometry import Polygon


class FakeReader(Reader):
    """Minimal reader for testing ExtractionJob validation."""

    def __call__(self, task):
        raise NotImplementedError


def test_job_no_search_or_task_builder():
    job = ExtractionJob(
        grid_config=GridConfig(target_grid_dist=1000),
        patch_config=PatchConfig(resolution=10.0),
        output_uri="/tmp/out",
        extract=ExtractConfig(read=FakeReader()),
    )
    assert not hasattr(job, "search")
    assert not hasattr(job, "task_builder")


def test_extraction_job_from_yaml_dict(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
name: s2_b04_over_my_aoi
grid_config:
  target_grid_dist: 50000
patch_config:
  resolution: 10.0
output_uri: "out_dir"
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
  reproject:
    _target_: aereo.builtins.ReprojectODC
    resampling: nearest
  write:
    _target_: aereo.builtins.WriteGeoTIFF
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.name == "s2_b04_over_my_aoi"
    assert job.output_uri == "out_dir"
    assert job.grid_config.target_grid_dist == 50000
    assert job.extract.read is not None
    assert job.extract.reproject is not None
    assert job.extract.write is not None


def test_extraction_job_from_yaml_target(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
_target_: aereo.pipeline.ExtractionJob
grid_config:
  _target_: aereo.interfaces.GridConfig
  target_grid_dist: 10000
patch_config:
  _target_: aereo.interfaces.PatchConfig
  resolution: 10.0
output_uri: "out_dir"
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.output_uri == "out_dir"
    assert job.grid_config.target_grid_dist == 10000
    assert job.extract.read is not None


def test_extraction_job_from_yaml_invalid(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
grid_config:
  _target_: aereo.interfaces.GridConfig
  # missing target_grid_dist
patch_config:
  _target_: aereo.interfaces.PatchConfig
  resolution: 10.0
output_uri: "out_dir"
extract: {}
"""
    )
    # Pydantic or Hydra will raise ValidationError or InstantiationException
    with pytest.raises(Exception):
        ExtractionJob.from_yaml(job_yaml)


def test_extraction_job_from_yaml_with_batch_writer(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
grid_config:
  _target_: aereo.interfaces.GridConfig
  target_grid_dist: 50000
patch_config:
  _target_: aereo.interfaces.PatchConfig
  resolution: 10.0
output_uri: "out_dir"
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
  reproject:
    _target_: aereo.builtins.ReprojectODC
  write:
    _target_: aereo.builtins.BatchWriteGeoTIFF
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    from aereo.interfaces import BatchWriter

    assert isinstance(job.extract.write, BatchWriter)


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
  - grid_config: default
  - patch_config: base
  - _self_

output_uri: "out_dir"
target_aoi:
  type: Polygon
  coordinates:
    - [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
"""
    )

    grid_dir = config_dir / "grid_config"
    grid_dir.mkdir()
    (grid_dir / "default.yaml").write_text(
        "_target_: aereo.interfaces.GridConfig\ntarget_grid_dist: 75000\n"
    )

    patch_dir = config_dir / "patch_config"
    patch_dir.mkdir()
    (patch_dir / "base.yaml").write_text(
        "_target_: aereo.interfaces.PatchConfig\nresolution: 20.0\n"
    )

    job = ExtractionJob.load_from_config(config_dir)
    assert job.output_uri == "out_dir"
    assert job.grid_config.target_grid_dist == 75_000
    assert job.patch_config.resolution == 20.0
    assert isinstance(job.target_aoi, Polygon)


def test_extraction_job_load_from_config_package_with_override(tmp_path: Path):
    config_dir = tmp_path / "conf"
    config_dir.mkdir()

    (config_dir / "main_config.yaml").write_text(
        """
defaults:
  - patch_config: base
  - _self_

grid_config:
  _target_: aereo.interfaces.GridConfig
  target_grid_dist: 50000
output_uri: "out_dir"
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
"""
    )

    patch_dir = config_dir / "patch_config"
    patch_dir.mkdir()
    (patch_dir / "base.yaml").write_text(
        "_target_: aereo.interfaces.PatchConfig\nresolution: 10.0\n"
    )
    (patch_dir / "high_res.yaml").write_text(
        "_target_: aereo.interfaces.PatchConfig\nresolution: 5.0\n"
    )

    job = ExtractionJob.load_from_config(
        config_dir, overrides=["patch_config=high_res"]
    )
    assert job.patch_config.resolution == 5.0


def test_extraction_job_load_from_config_package_without_targets(tmp_path: Path):
    """Concrete Pydantic models do not need ``_target_`` in Hydra configs."""
    config_dir = tmp_path / "conf"
    config_dir.mkdir()

    (config_dir / "main_config.yaml").write_text(
        """
defaults:
  - grid_config: default
  - patch_config: base
  - _self_

output_uri: "out_dir"
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
"""
    )

    grid_dir = config_dir / "grid_config"
    grid_dir.mkdir()
    (grid_dir / "default.yaml").write_text("target_grid_dist: 75000\n")

    patch_dir = config_dir / "patch_config"
    patch_dir.mkdir()
    (patch_dir / "base.yaml").write_text("resolution: 20.0\n")

    job = ExtractionJob.load_from_config(config_dir)
    assert isinstance(job.grid_config, GridConfig)
    assert job.grid_config.target_grid_dist == 75_000
    assert isinstance(job.patch_config, PatchConfig)
    assert job.patch_config.resolution == 20.0


def test_extraction_job_accepts_geojson_dict(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
grid_config:
  target_grid_dist: 50000
patch_config:
  resolution: 10.0
output_uri: "out_dir"
target_aoi:
  type: Polygon
  coordinates:
    - [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
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
grid_config:
  _target_: aereo.interfaces.GridConfig
  target_grid_dist: 50000
patch_config:
  _target_: aereo.interfaces.PatchConfig
  resolution: 10.0
output_uri: "out_dir"
target_aoi: {aoi_file}
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert isinstance(job.target_aoi, Polygon)


def test_extraction_job_target_aoi_defaults_to_none(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
grid_config:
  _target_: aereo.interfaces.GridConfig
  target_grid_dist: 50000
patch_config:
  _target_: aereo.interfaces.PatchConfig
  resolution: 10.0
output_uri: "out_dir"
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.target_aoi is None
    assert job.effective_target_aoi is None
