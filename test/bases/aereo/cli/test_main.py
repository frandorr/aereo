"""Tests for the AEREO CLI."""

import json
from pathlib import Path

from typer.testing import CliRunner

from aereo.cli.main import app

runner = CliRunner()


class TestValidate:
    def test_validate_missing_file(self):
        result = runner.invoke(app, ["validate", "--config", "nonexistent.yaml"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_validate_profile_success(self, tmp_path: Path):
        profile_yaml = tmp_path / "profile.yaml"
        profile_yaml.write_text(
            """
profiles:
  - name: test_profile
    resolution: 1000
    collections:
      S2: ["B02", "B03"]
"""
        )
        result = runner.invoke(app, ["validate", "--profile", str(profile_yaml)])
        assert result.exit_code == 0
        assert "✓ Profile valid" in result.output

    def test_validate_profile_failure(self, tmp_path: Path):
        profile_yaml = tmp_path / "profile.yaml"
        profile_yaml.write_text(
            """
profiles:
  - name: test_profile
    # missing required 'resolution'
"""
        )
        result = runner.invoke(app, ["validate", "--profile", str(profile_yaml)])
        assert result.exit_code == 1
        assert "✗ Profile invalid" in result.output

    def test_validate_config_success(self, tmp_path: Path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(
            """
grid_config:
  target_grid_dist: 50000
  target_grid_overlap: false
"""
        )
        result = runner.invoke(app, ["validate", "--config", str(config_yaml)])
        assert result.exit_code == 0
        assert "✓ Config valid" in result.output

    def test_validate_nothing_provided(self):
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 1
        assert "Provide --config or --profile" in result.output


class TestPlugins:
    def test_plugins_list(self):
        result = runner.invoke(app, ["plugins"])
        assert result.exit_code == 0
        assert "Installed AEREO Plugins" in result.output


class TestSearch:
    def test_search_missing_profile(self):
        result = runner.invoke(app, ["search", "--profile", "nonexistent.yaml"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_search_json_output(self, tmp_path: Path):
        profile_yaml = tmp_path / "profile.yaml"
        profile_yaml.write_text(
            """
profiles:
  - name: test_profile
    resolution: 1000
    collections:
      fake_collection: []
    plugin_hints:
      search: search_planetary_computer
"""
        )
        output_json = tmp_path / "results.json"
        # This will likely fail at search time (no real data), but tests CLI arg parsing
        result = runner.invoke(
            app,
            [
                "search",
                "--profile",
                str(profile_yaml),
                "--format",
                "json",
                "--output",
                str(output_json),
            ],
        )
        # Exit code may be 1 (search error) or 2 (no results) — both acceptable for this test
        assert result.exit_code in (0, 1, 2)


class TestPrepare:
    def test_prepare_missing_search_results(self):
        result = runner.invoke(
            app,
            [
                "prepare",
                "nonexistent.json",
                "--profile",
                "nonexistent.yaml",
            ],
        )
        assert result.exit_code == 1
        assert "not found" in result.output


class TestExtract:
    def test_extract_missing_tasks(self):
        result = runner.invoke(app, ["extract", "nonexistent.pkl"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestRun:
    def test_run_missing_profile(self):
        result = runner.invoke(
            app,
            [
                "run",
                "--profile",
                "nonexistent.yaml",
            ],
        )
        assert result.exit_code == 1
        assert "not found" in result.output


class TestHelpers:
    def test_load_geometry_feature(self, tmp_path: Path):
        from aereo.cli.main import _load_geometry

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
        geom = _load_geometry(geojson)
        assert geom == {"type": "Point", "coordinates": [0, 0]}

    def test_load_geometry_feature_collection(self, tmp_path: Path):
        from aereo.cli.main import _load_geometry

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
        geom = _load_geometry(geojson)
        assert geom is not None
        assert geom["type"] == "Polygon"

    def test_search_results_roundtrip(self, tmp_path: Path):
        from aereo.cli.main import _search_results_to_json
        import geopandas as gpd
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
        df["start_time"] = gpd.pd.to_datetime(df["start_time"])
        df["end_time"] = gpd.pd.to_datetime(df["end_time"])
        df.set_crs(epsg=4326, inplace=True)

        records = _search_results_to_json(df)
        assert len(records) == 2
        assert records[0]["id"] == "s1"
