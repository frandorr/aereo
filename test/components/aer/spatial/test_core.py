import pytest
from shapely.geometry import Polygon, Point
from pyresample.geometry import AreaDefinition
import geopandas as gpd

from aer.spatial import (
    reproject_geom,
    GridCell,
    GridDefinition,
    GridSchema,
)


@pytest.fixture
def sample_polygon():
    return Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)])


@pytest.fixture
def sample_grid_cell(sample_polygon):
    return GridCell(
        grid_cell="A_1",
        utm_footprint=sample_polygon,
        utm_crs="EPSG:32631",
        dist=100000,
    )


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
