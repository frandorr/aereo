"""Tests for the spatial component core models.

Verifies GridCell, GridDefinition, GridSchema validation, polygon reprojection,
and pyresample AreaDefinition generation.
"""

import json
import pytest
from shapely.geometry import Polygon, Point
from pyresample.geometry import AreaDefinition
import geopandas as gpd

from aer.spatial import (
    reproject_geom,
    GridCell,
    GridDefinition,
    GridSchema,
    format_intersects,
)


@pytest.fixture
def sample_polygon():
    return Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)])


@pytest.fixture
def sample_grid_cell(sample_polygon):
    return GridCell(
        grid_cell="A_1",
        footprint=sample_polygon,
        utm_footprint=sample_polygon,
        utm_crs="EPSG:32631",
        dist=100000,
    )


@pytest.fixture
def sample_geojson_feature():
    """A GeoJSON Feature object."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
        },
        "properties": {"name": "test"},
    }


@pytest.fixture
def sample_geojson_polygon():
    """A plain GeoJSON Polygon (not a Feature)."""
    return {
        "type": "Polygon",
        "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
    }


def test_reproject_polygon(sample_polygon):
    reprojected = reproject_geom(sample_polygon, "EPSG:4326", "EPSG:32631")
    assert isinstance(reprojected, Polygon)
    assert reprojected.bounds[2] > 1000


def test_grid_cell_area_name(sample_grid_cell):
    name = sample_grid_cell.area_name(resolution=500)
    assert name == "A_1_dist-100000m_res-500m"


def test_grid_cell_area_def(sample_grid_cell):
    area_def = sample_grid_cell.area_def(resolution=500)
    assert isinstance(area_def, AreaDefinition)
    assert area_def.area_id == "A_1_dist-100000m_res-500m"
    assert area_def.width == 100000 // 500
    assert area_def.height == 100000 // 500


def test_grid_definition_init():
    grid_def = GridDefinition(name="TestGrid", dist=100000, extent=(-180, -90, 180, 90))
    assert grid_def.name == "TestGrid"
    assert grid_def.dist == 100000
    assert grid_def.extent == (-180, -90, 180, 90)


def test_grid_definition_default_utm_definition():
    grid_def = GridDefinition(name="TestGrid", dist=100000)
    assert grid_def.utm_definition == "center"


def test_grid_definition_custom_utm_definition():
    grid_def = GridDefinition(name="TestGrid", dist=100000, utm_definition="bottomleft")
    assert grid_def.utm_definition == "bottomleft"


def test_grid_schema_validation():
    import pandas as pd

    df = pd.DataFrame(
        {
            "grid_cell": ["89D_36L"],
            "row": ["89D"],
            "col": ["36L"],
            "utm_crs": ["EPSG:32701"],
            "dist": [100000],
        }
    )
    gdf = gpd.GeoDataFrame(
        df,
        geometry=[Point(-180, -79.70149)],
    )
    gdf["utm_footprint"] = gpd.GeoSeries(
        [Polygon([(-180, -79.701), (-180, -78.806), (-175, -78.806), (-175, -79.701)])]
    )

    validated_gdf = GridSchema.validate(gdf)
    assert not validated_gdf.empty
    assert "grid_cell" in validated_gdf.columns
    assert validated_gdf.iloc[0]["grid_cell"] == "89D_36L"


class TestFormatIntersects:
    """Tests for format_intersects function."""

    def test_format_intersects_none(self):
        """Test that None returns None."""
        result = format_intersects(None)
        assert result is None

    def test_format_intersects_geojson_feature(self, sample_geojson_feature):
        """Test that GeoJSON Feature extracts geometry."""
        result = format_intersects(sample_geojson_feature)
        assert result is not None
        assert result["type"] == "Polygon"
        assert "coordinates" in result

    def test_format_intersects_geojson_polygon(self, sample_geojson_polygon):
        """Test that plain GeoJSON Polygon is returned as-is."""
        result = format_intersects(sample_geojson_polygon)
        assert result is not None
        assert result["type"] == "Polygon"
        assert result == sample_geojson_polygon

    def test_format_intersects_json_string(self, sample_geojson_polygon):
        """Test that JSON string is parsed and returned as dict."""
        json_str = json.dumps(sample_geojson_polygon)
        result = format_intersects(json_str)

        assert result is not None
        assert result["type"] == "Polygon"
        assert result == sample_geojson_polygon

    def test_format_intersects_geo_interface(self):
        """Test that objects with __geo_interface__ are handled."""

        class GeoInterfaceObj:
            @property
            def __geo_interface__(self):
                return {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                }

        obj = GeoInterfaceObj()
        result = format_intersects(obj)

        assert result is not None
        assert result["type"] == "Polygon"

    def test_format_intersects_invalid_type_raises(self):
        """Test that invalid types raise an exception."""
        with pytest.raises(Exception, match="intersects must be"):
            format_intersects(12345)  # type: ignore[arg-type]

    def test_format_intersects_returns_deep_copy(self):
        """Test that returned dict is a deep copy (not mutated on input change)."""
        original = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
        }
        result = format_intersects(original)

        assert result is not None  # type: ignore[assert]

        # Modify original
        original["type"] = "Point"

        # Result should be unchanged (deep copy)
        assert result["type"] == "Polygon"

    def test_format_intersects_polygon_shapely(self):
        """Test that Shapely Polygon objects with __geo_interface__ work."""
        polygon = Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)])
        result = format_intersects(polygon)

        assert result is not None
        assert result["type"] == "Polygon"
        assert "coordinates" in result
