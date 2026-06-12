from pathlib import Path

import pytest
from aereo.builtins import SearchSTAC
from aereo.pipeline import ExtractionJob
from shapely.geometry import Polygon


def test_extraction_job_from_yaml_dict(tmp_path: Path):
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
    resampling: nearest
  write:
    _target_: aereo.builtins.WriteGeoTIFF
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.output_uri == "out_dir"
    assert job.grid_config.target_grid_dist == 50000
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
grid_config:
  _target_: aereo.interfaces.GridConfig
  target_grid_dist: 10000
patch_config:
  _target_: aereo.interfaces.PatchConfig
  resolution: 10.0
output_uri: "out_dir"
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
search:
  _target_: aereo.builtins.SearchSTAC
  # missing stac_api_url
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


def test_extraction_job_accepts_geojson_dict(tmp_path: Path):
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
target_aoi:
  type: Polygon
  coordinates:
    - [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]
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
    assert isinstance(job.target_aoi, Polygon)


def test_extraction_job_target_aoi_falls_back_to_search_intersects(tmp_path: Path):
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
search:
  _target_: aereo.builtins.SearchSTAC
  stac_api_url: "https://planetarycomputer.microsoft.com/api/stac/v1"
  collections:
    sentinel-2-l2a: ["B04"]
  intersects: {aoi_file}
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
"""
    )
    job = ExtractionJob.from_yaml(job_yaml)
    assert job.target_aoi is None
    assert isinstance(job.search.intersects, Polygon)
    assert job.effective_target_aoi is job.search.intersects
