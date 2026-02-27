import pytest
from shapely.geometry import Polygon, Point
from pyresample.geometry import AreaDefinition
import geopandas as gpd
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from aer.spatial.core import (
    reproject_polygon,
    GridCell,
    GridSpatialExtent,
    GridDefinition,
)


@pytest.fixture
def sample_polygon():
    # A simple square polygon roughly near equator
    return Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)])


@pytest.fixture
def sample_grid_cell(sample_polygon):
    return GridCell(
        row="A", col="1", dist=100, bounds=sample_polygon, epsg="epsg:32631"
    )


def test_reproject_polygon(sample_polygon):
    # Reproject from standard WGS84 to UTM (roughly mapping an equatorial degree to meters)
    reprojected = reproject_polygon(sample_polygon, "epsg:4326", "epsg:32631")

    assert isinstance(reprojected, Polygon)
    # The bounding box should change from roughly 0-1 degrees to much larger numbers in meters
    assert reprojected.bounds[2] > 1000


def test_grid_cell_utm_bounds(sample_grid_cell):
    utm_bounds = sample_grid_cell.utm_bounds
    assert isinstance(utm_bounds, Polygon)
    assert (
        utm_bounds.bounds != sample_grid_cell.bounds.bounds
    )  # bounds should be different


def test_grid_cell_area_name(sample_grid_cell):
    name = sample_grid_cell.area_name(resolution=500)
    assert name == "A_1_100km_500m"


def test_grid_cell_area_def(sample_grid_cell):
    with patch(
        "aer.spatial.core.GridCell.utm_bounds", new_callable=PropertyMock
    ) as mock_bounds:
        # Mock bounds that cover 100km x 100km area
        mock_bounds.return_value = Polygon(
            [(0, 0), (0, 100000), (100000, 100000), (100000, 0), (0, 0)]
        )

        area_def = sample_grid_cell.area_def(resolution=500)
        assert isinstance(area_def, AreaDefinition)
        assert area_def.area_id == "A_1_100km_500m"
        assert area_def.width == 100 * 1000 // 500  # dist=100km, res=500m -> 200
        assert area_def.height == 200


def test_grid_spatial_extent():
    cell1 = GridCell(
        row="A",
        col="1",
        dist=10,
        bounds=Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]),
        epsg="epsg:32631",
    )
    cell2 = GridCell(
        row="A",
        col="2",
        dist=10,
        bounds=Polygon([(1, 0), (1, 1), (2, 1), (2, 0), (1, 0)]),
        epsg="epsg:32631",
    )
    cell3 = GridCell(
        row="B",
        col="1",
        dist=10,
        bounds=Polygon([(0, 1), (0, 2), (1, 2), (1, 1), (0, 1)]),
        epsg="epsg:32631",
    )

    extent1 = GridSpatialExtent(frozenset([cell1, cell2]))
    extent2 = GridSpatialExtent(frozenset([cell2, cell3]))
    extent3 = GridSpatialExtent(frozenset([cell3]))

    # test intersects
    assert extent1.intersects(extent2) is True
    assert extent1.intersects(extent3) is False

    # test intersection
    intersection = extent1.intersection(extent2)
    assert len(intersection.grid_cells) == 1
    assert list(intersection.grid_cells)[0] == cell2


def test_grid_definition_grid(monkeypatch):
    # Mock ENV_SETTINGS directly via monkeypatch
    mock_env = MagicMock()
    mock_env.GRID_STORE_PATH = Path("/tmp/mock_grid_store")
    monkeypatch.setattr("aer.spatial.core.ENV_SETTINGS", mock_env)

    grid_def = GridDefinition(name="TestGrid", dist=100)

    mock_gdf = gpd.GeoDataFrame(
        {
            "row": ["A"],
            "col": ["1"],
            "epsg": ["epsg:32631"],
            "geometry": [Point(0, 0)],
            "cell_bounds": [Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)])],
        }
    )

    with patch("geopandas.read_parquet", return_value=mock_gdf) as mock_read:
        grid = grid_def.grid
        mock_read.assert_called_once_with(
            Path("/tmp/mock_grid_store/grid_TestGrid_100km.parquet")
        )
        assert not grid.empty
        assert len(grid) == 1


def test_grid_definition_grid_empty(monkeypatch):
    mock_env = MagicMock()
    mock_env.GRID_STORE_PATH = Path("/tmp/mock_grid_store")
    monkeypatch.setattr("aer.spatial.core.ENV_SETTINGS", mock_env)

    grid_def = GridDefinition(name="TestGrid", dist=100)
    mock_empty_gdf = gpd.GeoDataFrame()

    with patch("geopandas.read_parquet", return_value=mock_empty_gdf):
        with pytest.raises(ValueError, match="is empty"):
            _ = grid_def.grid


def test_grid_definition_intersecting_grid_spatial_extent():
    grid_def = GridDefinition(name="TestGrid", dist=100)

    # Mock the grid property to return a GeoDataFrame
    mock_gdf = gpd.GeoDataFrame(
        {
            "row": ["A", "A", "B"],
            "col": ["1", "2", "1"],
            "epsg": ["epsg:32631", "epsg:32631", "epsg:32631"],
            "geometry": [
                Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]),
                Polygon([(1, 0), (1, 1), (2, 1), (2, 0), (1, 0)]),
                Polygon([(0, 1), (0, 2), (1, 2), (1, 1), (0, 1)]),
            ],
            "cell_bounds": [
                Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]),
                Polygon([(1, 0), (1, 1), (2, 1), (2, 0), (1, 0)]),
                Polygon([(0, 1), (0, 2), (1, 2), (1, 1), (0, 1)]),
            ],
        }
    )

    with patch(
        "aer.spatial.core.GridDefinition.grid",
        new_callable=PropertyMock,
        return_value=mock_gdf,
    ):
        # A geometry fully contained within A1, slightly touching A2 boundary?
        # A buffer on Point(0.5, 0.5) will only intersect A1
        test_poly = Point(0.5, 0.5).buffer(0.1)
        extent = grid_def.intersecting_grid_spatial_extent(test_poly)

        assert isinstance(extent, GridSpatialExtent)
        assert len(extent.grid_cells) == 1
        cell = list(extent.grid_cells)[0]
        assert cell.row == "A"
        assert cell.col == "1"
        assert cell.dist == 100

        # Test poly intersecting two cells
        test_poly2 = Point(1, 0.5).buffer(0.1)
        extent2 = grid_def.intersecting_grid_spatial_extent(test_poly2)
        assert len(extent2.grid_cells) == 2
        rows_cols = set((c.row, c.col) for c in extent2.grid_cells)
        assert rows_cols == {("A", "1"), ("A", "2")}
