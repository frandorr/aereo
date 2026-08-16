"""Tests for the job configuration snapshot guard."""

from functools import partial
from pathlib import Path

import pytest
import yaml
from aereo.jobguard import (
    JobConfigMismatchError,
    canonicalize_job,
    check_job_snapshot,
    snapshot_uri_for,
)
from aereo.pipeline import ExtractionJob
from shapely.geometry import box


def _fake_reader(**kwargs):
    """Fake reader callable for snapshot tests."""
    raise NotImplementedError


def _fake_writer(ds, path, **kwargs):
    """Fake writer callable for snapshot tests."""
    raise NotImplementedError


def _fake_search(**kwargs):
    """Fake search provider for snapshot tests."""
    raise NotImplementedError


def _make_job(output_uri: str, **overrides) -> ExtractionJob:
    """Build a minimal job with a partial-bound search provider."""
    kwargs = {
        "name": "test_job",
        "grid_dist": 1000,
        "grid_resolution": 10.0,
        "output_uri": output_uri,
        "read": partial(_fake_reader),
        "write": partial(_fake_writer),
        "search_provider": partial(
            _fake_search,
            collections={"sentinel-2-l2a": ["red", "nir"]},
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-10T00:00:00Z",
            intersects="some-aoi",
        ),
    }
    kwargs.update(overrides)
    return ExtractionJob(**kwargs)


def test_canonicalize_job_excludes_runtime_and_extent_fields(tmp_path: Path):
    job = _make_job(
        str(tmp_path),
        overwrite=True,
        target_aoi=box(0, 0, 1, 1),
    )
    snapshot = canonicalize_job(job)
    assert "name" not in snapshot
    assert "output_uri" not in snapshot
    assert "overwrite" not in snapshot
    assert "target_aoi" not in snapshot
    assert snapshot["grid_dist"] == 1000
    assert snapshot["grid_resolution"] == 10.0
    search = snapshot["search_provider"]
    assert search["collections"] == {"sentinel-2-l2a": ["red", "nir"]}
    assert "start_datetime" not in search
    assert "end_datetime" not in search
    assert "intersects" not in search


def test_snapshot_written_on_first_run(tmp_path: Path):
    job = _make_job(str(tmp_path))
    uri = check_job_snapshot(job)
    expected = tmp_path / "job-test_job" / "job.yaml"
    assert uri == str(expected)
    assert expected.exists()
    loaded = yaml.safe_load(expected.read_text())
    assert loaded == canonicalize_job(job)


def test_identical_rerun_passes(tmp_path: Path):
    check_job_snapshot(_make_job(str(tmp_path)))
    uri = check_job_snapshot(_make_job(str(tmp_path)))
    assert uri is not None


def test_yaml_and_in_code_jobs_are_equivalent(tmp_path: Path):
    job_yaml = tmp_path / "job.yaml"
    out_dir = tmp_path / "out"
    job_yaml.write_text(
        f"""
# a comment that must not affect identity
helper_bands: [red, nir]

name: test_job
grid_dist: 1000
resolution: 10.0
output_uri: "{out_dir}"
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
search:
  _target_: aereo.builtins.search.search_stac
  collections:
    sentinel-2-l2a: ${{helper_bands}}
  start_datetime: "2024-01-01T00:00:00Z"
  end_datetime: "2024-01-10T00:00:00Z"
"""
    )
    from aereo.builtins.read import read_odc_stac
    from aereo.builtins.search import search_stac
    from aereo.builtins.write import write_geotiff

    yaml_job = ExtractionJob.from_yaml(job_yaml)
    in_code_job = ExtractionJob(
        name="test_job",
        grid_dist=1000,
        grid_resolution=10.0,
        output_uri=str(out_dir),
        read=partial(read_odc_stac),
        write=partial(write_geotiff),
        search_provider=partial(
            search_stac,
            collections={"sentinel-2-l2a": ["red", "nir"]},
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-10T00:00:00Z",
        ),
    )
    assert canonicalize_job(yaml_job) == canonicalize_job(in_code_job)
    check_job_snapshot(yaml_job)
    assert check_job_snapshot(in_code_job) is not None


def test_mismatch_on_band_change_raises(tmp_path: Path):
    check_job_snapshot(_make_job(str(tmp_path)))
    changed = _make_job(
        str(tmp_path),
        search_provider=partial(
            _fake_search, collections={"sentinel-2-l2a": ["B08", "B11"]}
        ),
    )
    with pytest.raises(JobConfigMismatchError) as excinfo:
        check_job_snapshot(changed)
    message = str(excinfo.value)
    assert "collections" in message
    assert "B08" in message
    assert "Rename the job" in message


def test_mismatch_on_resolution_change_raises(tmp_path: Path):
    check_job_snapshot(_make_job(str(tmp_path)))
    with pytest.raises(JobConfigMismatchError) as excinfo:
        check_job_snapshot(_make_job(str(tmp_path), grid_resolution=20.0))
    assert "grid_resolution" in str(excinfo.value)


def test_mismatch_on_callable_change_raises(tmp_path: Path):
    check_job_snapshot(_make_job(str(tmp_path)))
    changed = _make_job(str(tmp_path), write=partial(_fake_reader))
    with pytest.raises(JobConfigMismatchError) as excinfo:
        check_job_snapshot(changed)
    assert "write" in str(excinfo.value)


def test_extent_only_change_passes(tmp_path: Path):
    check_job_snapshot(_make_job(str(tmp_path)))
    extended = _make_job(
        str(tmp_path),
        target_aoi=box(5, 5, 6, 6),
        search_provider=partial(
            _fake_search,
            collections={"sentinel-2-l2a": ["red", "nir"]},
            start_datetime="2025-06-01T00:00:00Z",
            end_datetime="2025-06-30T00:00:00Z",
            intersects="a-different-aoi",
        ),
    )
    assert check_job_snapshot(extended) is not None


def test_snapshot_uri_for_sanitizes_job_name():
    uri = snapshot_uri_for("/data/out", "my job/v2")
    assert uri == "/data/out/job-my_job_v2/job.yaml"


def test_guard_skips_when_filesystem_unavailable(tmp_path: Path, monkeypatch):
    import fsspec.core

    def _boom(uri):
        raise ImportError("missing s3fs")

    monkeypatch.setattr(fsspec.core, "url_to_fs", _boom)
    job = _make_job(str(tmp_path))
    assert check_job_snapshot(job) is None
