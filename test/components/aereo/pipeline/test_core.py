from pathlib import Path
import pytest
from aereo.builtins import SearchSTAC
from aereo.pipeline import ExtractionJob


def test_extraction_job_from_yaml_dict(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
global:
  grid_config:
    _target_: aereo.interfaces.GridConfig
    target_grid_dist: 50000
  patch_config:
    _target_: aereo.interfaces.PatchConfig
    resolution: 10.0
  uri: "out_dir"
search:
  _target_: aereo.builtins.SearchSTAC
  stac_api_url: "https://planetarycomputer.microsoft.com/api/stac/v1"
  collections:
    sentinel-2-l2a: ["B04"]
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
  reproject:
    _target_: aereo.builtins.ReprojectODC
    resolution: 10.0
    resampling: nearest
  write:
    _target_: aereo.builtins.WriteGeoTIFF
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.global_config.uri == "out_dir"
    assert job.global_config.grid_config.target_grid_dist == 50000
    assert job.extract.read is not None
    assert job.extract.reproject is not None
    assert job.extract.write is not None
    assert isinstance(job.search, SearchSTAC)
    assert (
        job.search.stac_api_url == "https://planetarycomputer.microsoft.com/api/stac/v1"
    )


def test_extraction_job_from_yaml_target(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
_target_: aereo.pipeline.ExtractionJob
global:
  grid_config:
    _target_: aereo.interfaces.GridConfig
    target_grid_dist: 10000
  patch_config:
    _target_: aereo.interfaces.PatchConfig
    resolution: 10.0
  uri: "out_dir"
search:
  _target_: aereo.builtins.SearchSTAC
  stac_api_url: "https://planetarycomputer.microsoft.com/api/stac/v1"
  collections:
    sentinel-2-l2a: ["B04"]
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.global_config.uri == "out_dir"
    assert job.global_config.grid_config.target_grid_dist == 10000
    assert job.extract.read is not None


def test_extraction_job_from_yaml_invalid(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
global: {}
search:
  _target_: aereo.builtins.SearchSTAC
  # missing stac_api_url
extract: {}
"""
    )
    # Pydantic or Hydra will raise ValidationError or InstantiationException
    with pytest.raises(Exception):
        ExtractionJob.from_yaml(job_yaml)
