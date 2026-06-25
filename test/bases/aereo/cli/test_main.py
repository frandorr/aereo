"""Tests for the AEREO CLI using Hydra."""

import json
from pathlib import Path
import pytest
from hydra import initialize_config_dir, compose
from aereo.cli.main import main


def run_cli_config(config_dir: Path, config_name: str, overrides: list[str]) -> None:
    """Helper to initialize and execute main with composed Hydra config."""
    # Ensure config_dir is absolute
    config_dir_abs = str(config_dir.resolve())
    with initialize_config_dir(version_base=None, config_dir=config_dir_abs):
        cfg = compose(config_name=config_name, overrides=overrides)
        main(cfg)


class TestValidate:
    def test_validate_success(self, tmp_path: Path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(
            """
action: validate
verbose: false
search:
  _target_: aereo.builtins.SearchSTAC
  stac_api_url: "https://stac"
  collections:
    s2: []
task_builder:
  _target_: aereo.builtins.task_builder.GroupedTaskBuilder
  cells_per_task: 50
grid_config:
  _target_: aereo.interfaces.GridConfig
  target_grid_dist: 50000
patch_config:
  _target_: aereo.interfaces.PatchConfig
  resolution: 10.0
output_uri: "out"
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
  reproject:
    _target_: aereo.builtins.ReprojectODC
  write:
    _target_: aereo.builtins.WriteGeoTIFF
"""
        )
        run_cli_config(tmp_path, "config", [])

    def test_validate_failure(self, tmp_path: Path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(
            """
action: validate
verbose: false
search:
  _target_: aereo.builtins.SearchSTAC
  # missing stac_api_url (required for SearchSTAC)
  collections:
    s2: []
"""
        )
        with pytest.raises(SystemExit) as excinfo:
            run_cli_config(tmp_path, "config", [])
        assert excinfo.value.code == 1


class TestPlugins:
    def test_plugins_list(self, tmp_path: Path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("action: plugins\nverbose: false\n")
        run_cli_config(tmp_path, "config", [])


class TestSearch:
    def test_search_missing_search_config(self, tmp_path: Path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(
            """
action: search
verbose: false
search: null
"""
        )
        with pytest.raises(SystemExit) as excinfo:
            run_cli_config(tmp_path, "config", [])
        assert excinfo.value.code == 1


class TestBuildTasks:
    def test_build_tasks_missing_search_results(self, tmp_path: Path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(
            """
action: build-tasks
verbose: false
search_results: null
"""
        )
        with pytest.raises(SystemExit) as excinfo:
            run_cli_config(tmp_path, "config", [])
        assert excinfo.value.code == 1


class TestExtract:
    def test_extract_missing_tasks(self, tmp_path: Path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(
            """
action: extract
verbose: false
tasks: null
"""
        )
        with pytest.raises(SystemExit) as excinfo:
            run_cli_config(tmp_path, "config", [])
        assert excinfo.value.code == 1


class TestRun:
    def test_run_missing_search(self, tmp_path: Path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(
            """
action: run
verbose: false
search: null
"""
        )
        with pytest.raises(SystemExit) as excinfo:
            run_cli_config(tmp_path, "config", [])
        assert excinfo.value.code == 1


class TestHelpers:
    def test_load_geometry_feature(self, tmp_path: Path):
        from aereo.cli.main import _load_geometry_safe
        from shapely.geometry import Point

        geojson = tmp_path / "aoi.geojson"
        geojson.write_text(
            json.dumps(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [0, 0],
                    },
                }
            )
        )
        geom = _load_geometry_safe(geojson)
        assert isinstance(geom, Point)
        assert geom.x == 0.0
        assert geom.y == 0.0

    def test_load_geometry_feature_collection(self, tmp_path: Path):
        from aereo.cli.main import _load_geometry_safe
        from shapely.geometry import Polygon

        geojson = tmp_path / "aoi.geojson"
        geojson.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
                                ],
                            },
                        }
                    ],
                }
            )
        )
        geom = _load_geometry_safe(geojson)
        assert isinstance(geom, Polygon)
        assert geom.is_valid

    def test_search_results_roundtrip(self, tmp_path: Path):
        from aereo.cli.main import _search_results_to_json
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import Point

        df = gpd.GeoDataFrame(
            {
                "id": ["s1", "s2"],
                "collection": ["c1", "c2"],
                "start_time": ["2024-01-01T00:00:00", "2024-01-02T00:00:00"],
                "end_time": ["2024-01-01T23:59:59", "2024-01-02T23:59:59"],
                "href": ["http://a", "http://b"],
                "geometry": [Point(0, 0), Point(1, 1)],
            }
        )
        df["start_time"] = pd.to_datetime(df["start_time"])
        df["end_time"] = pd.to_datetime(df["end_time"])
        df.set_crs(epsg=4326, inplace=True)

        records = _search_results_to_json(df)
        assert len(records) == 2
        assert records[0]["id"] == "s1"
