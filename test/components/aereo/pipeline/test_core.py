from pathlib import Path
import pytest
from aereo.builtins import SearchSTAC
from aereo.pipeline import ExtractionJob


def test_extraction_job_from_yaml_dict(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
search:
  _target_: aereo.builtins.SearchSTAC
  stac_api_url: "https://planetarycomputer.microsoft.com/api/stac/v1"
  collections:
    sentinel-2-l2a: ["B04"]
pipeline:
  - _target_: aereo.builtins.ReadODCSTAC
  - _target_: aereo.builtins.ReprojectODC
    resolution: 10.0
    resampling: nearest
  - _target_: aereo.builtins.WriteGeoTIFF
grid_config:
  target_grid_dist: 50000
uri: "out_dir"
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.uri == "out_dir"
    assert job.grid_config.target_grid_dist == 50000
    assert len(job.pipeline) == 3
    assert isinstance(job.search, SearchSTAC)
    assert (
        job.search.stac_api_url == "https://planetarycomputer.microsoft.com/api/stac/v1"
    )


def test_extraction_job_from_yaml_target(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
_target_: aereo.pipeline.ExtractionJob
search:
  _target_: aereo.builtins.SearchSTAC
  stac_api_url: "https://planetarycomputer.microsoft.com/api/stac/v1"
  collections:
    sentinel-2-l2a: ["B04"]
pipeline:
  - _target_: aereo.builtins.ReadODCSTAC
grid_config:
  _target_: aereo.interfaces.GridConfig
  target_grid_dist: 10000
uri: "out_dir"
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.uri == "out_dir"
    assert job.grid_config.target_grid_dist == 10000
    assert len(job.pipeline) == 1


def test_extraction_job_from_yaml_invalid(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
search:
  _target_: aereo.builtins.SearchSTAC
  # missing stac_api_url
pipeline: []
grid_config: {}
uri: "out_dir"
"""
    )
    # Pydantic or Hydra will raise ValidationError or InstantiationException
    with pytest.raises(Exception):
        ExtractionJob.from_yaml(job_yaml)
