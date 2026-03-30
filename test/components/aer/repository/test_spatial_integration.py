"""Integration tests for spatial repository workflow.

Covers end-to-end scenarios similar to user scripts:
GridDefinition -> AerParquetSpatialRepository -> get_grid_cells -> GridCell operations
"""

import tempfile
from pathlib import Path

import pytest
from shapely.geometry import box

from aer.repository.spatial import AerParquetSpatialRepository
from aer.spatial import GridCell, GridDefinition, OverlapMode


@pytest.fixture
def temp_grid_store():
    """Create a temporary directory for grid parquet files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def europe_grid_def():
    """Grid definition covering Europe with 200km cells."""
    return GridDefinition(
        name="europe_test",
        dist=200000,  # 200km in meters
        extent=(-10, 35, 30, 60),  # (min_lon, min_lat, max_lon, max_lat)
    )


@pytest.fixture
def repo(temp_grid_store):
    """Create a repository with a temporary grid store."""
    return AerParquetSpatialRepository(grid_store=temp_grid_store)


class TestGridCellCreation:
    """Tests for GridCell initialization and basic properties."""

    def test_grid_cell_with_polygon_footprint(self):
        """GridCell accepts Polygon utm_footprint."""
        from shapely.geometry import Polygon

        footprint = Polygon([(0, 0), (0, 100000), (100000, 100000), (100000, 0)])
        cell = GridCell(
            grid_cell="0U_0R",
            utm_footprint=footprint,
            utm_crs="EPSG:32631",
            dist=100000,
        )
        assert cell.grid_cell == "0U_0R"
        assert cell.utm_crs == "EPSG:32631"
        assert cell.dist == 100000

    def test_grid_cell_footprint_property_returns_utm_footprint(self):
        """footprint property returns the same as utm_footprint."""
        from shapely.geometry import Polygon

        footprint = Polygon([(0, 0), (0, 100000), (100000, 100000), (100000, 0)])
        cell = GridCell(
            grid_cell="0U_0R",
            utm_footprint=footprint,
            utm_crs="EPSG:32631",
            dist=100000,
        )
        assert cell.footprint is cell.utm_footprint
        assert cell.footprint.equals(footprint)

    def test_grid_cell_dist_is_integer(self):
        """dist attribute is stored as integer (meters)."""
        from shapely.geometry import Polygon

        footprint = Polygon([(0, 0), (0, 100000), (100000, 100000), (100000, 0)])
        cell = GridCell(
            grid_cell="0U_0R",
            utm_footprint=footprint,
            utm_crs="EPSG:32631",
            dist=200000,
        )
        assert isinstance(cell.dist, int)
        assert cell.dist == 200000


class TestGridCellAreaName:
    """Tests for GridCell.area_name method."""

    def test_area_name_format(self):
        """area_name returns formatted string with grid_cell, dist in meters, and resolution."""
        from shapely.geometry import Polygon

        footprint = Polygon([(0, 0), (0, 100000), (100000, 100000), (100000, 0)])
        cell = GridCell(
            grid_cell="0U_0R",
            utm_footprint=footprint,
            utm_crs="EPSG:32631",
            dist=200000,
        )
        name = cell.area_name(1000)
        assert name == "0U_0R_dist-200000m_res-1000m"

    def test_area_name_different_resolutions(self):
        """area_name works with various resolution values."""
        from shapely.geometry import Polygon

        footprint = Polygon([(0, 0), (0, 100000), (100000, 100000), (100000, 0)])
        cell = GridCell(
            grid_cell="1U_2R",
            utm_footprint=footprint,
            utm_crs="EPSG:32632",
            dist=500000,
        )
        assert cell.area_name(500) == "1U_2R_dist-500000m_res-500m"
        assert cell.area_name(2000) == "1U_2R_dist-500000m_res-2000m"
        assert cell.area_name(10000) == "1U_2R_dist-500000m_res-10000m"


class TestGridCellAreaDef:
    """Tests for GridCell.area_def method - regression tests for ZeroDivisionError."""

    def test_area_def_returns_area_definition(self):
        """area_def returns a valid pyresample AreaDefinition."""
        from pyresample.geometry import AreaDefinition
        from shapely.geometry import Polygon

        footprint = Polygon([(0, 0), (0, 200000), (200000, 200000), (200000, 0)])
        cell = GridCell(
            grid_cell="0U_0R",
            utm_footprint=footprint,
            utm_crs="EPSG:32631",
            dist=200000,
        )
        area_def = cell.area_def(1000)
        assert isinstance(area_def, AreaDefinition)

    def test_area_def_width_height_calculation(self):
        """area_def calculates correct width and height from dist and resolution."""
        from shapely.geometry import Polygon

        footprint = Polygon([(0, 0), (0, 200000), (200000, 200000), (200000, 0)])
        cell = GridCell(
            grid_cell="0U_0R",
            utm_footprint=footprint,
            utm_crs="EPSG:32631",
            dist=200000,
        )
        area_def = cell.area_def(1000)
        assert area_def.width == 200
        assert area_def.height == 200

    def test_area_def_with_different_resolutions(self):
        """area_def works with various resolution values."""
        from shapely.geometry import Polygon

        footprint = Polygon([(0, 0), (0, 200000), (200000, 200000), (200000, 0)])
        cell = GridCell(
            grid_cell="0U_0R",
            utm_footprint=footprint,
            utm_crs="EPSG:32631",
            dist=200000,
        )
        area_def_500 = cell.area_def(500)
        area_def_1000 = cell.area_def(1000)
        area_def_2000 = cell.area_def(2000)

        assert area_def_500.width == 400
        assert area_def_1000.width == 200
        assert area_def_2000.width == 100

    def test_area_def_area_extent_matches_footprint(self):
        """area_def area_extent matches the utm_footprint bounds."""
        from shapely.geometry import Polygon

        footprint = Polygon(
            [(100000, 200000), (100000, 400000), (300000, 400000), (300000, 200000)]
        )
        cell = GridCell(
            grid_cell="0U_0R",
            utm_footprint=footprint,
            utm_crs="EPSG:32631",
            dist=200000,
        )
        area_def = cell.area_def(1000)
        bounds = footprint.bounds
        assert area_def.area_extent == (bounds[0], bounds[1], bounds[2], bounds[3])

    def test_area_def_crs_matches_cell_crs(self):
        """area_def projection matches the cell's utm_crs."""
        from shapely.geometry import Polygon

        footprint = Polygon([(0, 0), (0, 200000), (200000, 200000), (200000, 0)])
        cell = GridCell(
            grid_cell="0U_0R",
            utm_footprint=footprint,
            utm_crs="EPSG:32633",
            dist=200000,
        )
        area_def = cell.area_def(1000)
        assert area_def.crs.to_epsg() == 32633

    def test_area_def_area_id_matches_area_name(self):
        """area_def area_id matches the cell's area_name."""
        from shapely.geometry import Polygon

        footprint = Polygon([(0, 0), (0, 200000), (200000, 200000), (200000, 0)])
        cell = GridCell(
            grid_cell="0U_0R",
            utm_footprint=footprint,
            utm_crs="EPSG:32631",
            dist=200000,
        )
        area_def = cell.area_def(1000)
        assert area_def.area_id == cell.area_name(1000)


class TestGridDefinition:
    """Tests for GridDefinition initialization and properties."""

    def test_grid_definition_with_meters_dist(self):
        """GridDefinition accepts integer dist in meters."""
        grid_def = GridDefinition(
            name="test",
            dist=200000,
            extent=(-10, 35, 30, 60),
        )
        assert grid_def.dist == 200000
        assert isinstance(grid_def.dist, int)

    def test_grid_definition_default_extent(self):
        """GridDefinition uses default extent when not provided."""
        grid_def = GridDefinition(name="test", dist=100000)
        assert grid_def.extent == (-180, -80, 180, 84)

    def test_grid_definition_default_utm_definition(self):
        """GridDefinition uses 'center' as default utm_definition."""
        grid_def = GridDefinition(name="test", dist=100000)
        assert grid_def.utm_definition == "center"


class TestAerParquetSpatialRepository:
    """Tests for AerParquetSpatialRepository end-to-end workflows."""

    def test_repo_creates_grid_on_first_access(self, repo, europe_grid_def):
        """Repository creates grid parquet file when it doesn't exist."""
        cells = repo.get_grid_cells(europe_grid_def)
        grid_path = repo.grid_store / f"{europe_grid_def.name}.parquet"
        assert grid_path.exists()
        assert len(cells) > 0

    def test_repo_returns_grid_cells(self, repo, europe_grid_def):
        """get_grid_cells returns a list of GridCell objects."""
        cells = repo.get_grid_cells(europe_grid_def)
        assert isinstance(cells, list)
        assert all(isinstance(cell, GridCell) for cell in cells)

    def test_repo_grid_cells_have_valid_properties(self, repo, europe_grid_def):
        """GridCells from repository have all required properties."""
        cells = repo.get_grid_cells(europe_grid_def)
        cell = cells[0]

        assert isinstance(cell.grid_cell, str)
        assert cell.utm_footprint is not None
        assert isinstance(cell.utm_crs, str)
        assert isinstance(cell.dist, int)
        assert cell.dist == europe_grid_def.dist

    def test_repo_grid_cells_area_def_works(self, repo, europe_grid_def):
        """GridCells from repository can create area_def without errors."""
        cells = repo.get_grid_cells(europe_grid_def)
        cell = cells[0]

        area_def = cell.area_def(1000)
        assert area_def is not None
        assert area_def.width > 0
        assert area_def.height > 0

    def test_repo_filters_by_intersects(self, repo, europe_grid_def):
        """get_grid_cells with INTERSECTS mode returns cells overlapping the geometry."""
        cells = repo.get_grid_cells(europe_grid_def)

        region = box(0, 45, 10, 50)
        filtered = repo.get_grid_cells(
            europe_grid_def,
            geometry=region,
            overlap_mode=OverlapMode.INTERSECTS,
        )

        assert len(filtered) > 0
        assert len(filtered) <= len(cells)

    def test_repo_filters_by_contains(self, repo, europe_grid_def):
        """get_grid_cells with CONTAINS mode returns cells fully inside geometry."""
        cells = repo.get_grid_cells(europe_grid_def)

        large_region = box(-20, 30, 40, 65)
        filtered = repo.get_grid_cells(
            europe_grid_def,
            geometry=large_region,
            overlap_mode=OverlapMode.CONTAINS,
        )

        assert len(filtered) <= len(cells)

    def test_repo_filters_by_within(self, repo, europe_grid_def):
        """get_grid_cells with WITHIN mode returns cells within geometry."""
        cells = repo.get_grid_cells(europe_grid_def)

        large_region = box(-20, 30, 40, 65)
        filtered = repo.get_grid_cells(
            europe_grid_def,
            geometry=large_region,
            overlap_mode=OverlapMode.WITHIN,
        )

        assert len(filtered) <= len(cells)

    def test_repo_no_filter_returns_all_cells(self, repo, europe_grid_def):
        """get_grid_cells without geometry returns all cells."""
        all_cells = repo.get_grid_cells(europe_grid_def)
        filtered_cells = repo.get_grid_cells(
            europe_grid_def, geometry=None, overlap_mode=None
        )
        assert len(all_cells) == len(filtered_cells)

    def test_repo_caches_grid(self, repo, europe_grid_def):
        """Repository caches loaded grids (LRU cache on _load_grid)."""
        grid1 = repo._load_grid(europe_grid_def)
        grid2 = repo._load_grid(europe_grid_def)
        assert grid1 is grid2

    def test_repo_reuses_existing_grid_file(self, repo, europe_grid_def):
        """Repository doesn't recreate grid if parquet file exists."""
        cells1 = repo.get_grid_cells(europe_grid_def)
        grid_path = repo.grid_store / f"{europe_grid_def.name}.parquet"
        original_mtime = grid_path.stat().st_mtime

        cells2 = repo.get_grid_cells(europe_grid_def)
        assert grid_path.stat().st_mtime == original_mtime
        assert len(cells1) == len(cells2)


class TestEndToEndWorkflow:
    """Tests mimicking real user script workflows."""

    def test_user_script_workflow_europe(self, temp_grid_store):
        """Full workflow: init repo, define grid, get cells, filter, use cell."""
        from pyresample.geometry import AreaDefinition

        repo = AerParquetSpatialRepository(grid_store=temp_grid_store)

        grid_def = GridDefinition(
            name="my_grid",
            dist=200000,  # 200km in meters
            extent=(-10, 35, 30, 60),
        )

        cells = repo.get_grid_cells(grid_def)
        assert len(cells) > 0

        region = box(-5, 40, 15, 55)
        filtered = repo.get_grid_cells(
            grid_def,
            geometry=region,
            overlap_mode=OverlapMode.INTERSECTS,
        )
        assert len(filtered) > 0

        cell = filtered[0]
        assert isinstance(cell.grid_cell, str)
        assert isinstance(cell.utm_crs, str)

        area_name = cell.area_name(1000)
        assert isinstance(area_name, str)

        area_def = cell.area_def(1000)
        assert isinstance(area_def, AreaDefinition)
        assert area_def.width > 0
        assert area_def.height > 0

    def test_user_script_workflow_small_dist(self, temp_grid_store):
        """Workflow with smaller grid cells (50km)."""
        repo = AerParquetSpatialRepository(grid_store=temp_grid_store)

        grid_def = GridDefinition(
            name="small_grid",
            dist=50000,  # 50km in meters
            extent=(0, 40, 10, 50),
        )

        cells = repo.get_grid_cells(grid_def)
        assert len(cells) > 0

        cell = cells[0]
        area_def = cell.area_def(1000)
        assert area_def.width > 0
        assert area_def.height > 0

    def test_user_script_workflow_large_dist(self, temp_grid_store):
        """Workflow with larger grid cells (500km)."""
        repo = AerParquetSpatialRepository(grid_store=temp_grid_store)

        grid_def = GridDefinition(
            name="large_grid",
            dist=500000,  # 500km in meters
            extent=(-10, 35, 30, 60),
        )

        cells = repo.get_grid_cells(grid_def)
        assert len(cells) > 0

        cell = cells[0]
        area_def = cell.area_def(2000)
        assert area_def.width > 0
        assert area_def.height > 0

    def test_footprint_property_matches_utm_footprint(self, temp_grid_store):
        """footprint property returns the same geometry as utm_footprint."""
        repo = AerParquetSpatialRepository(grid_store=temp_grid_store)

        grid_def = GridDefinition(
            name="footprint_test",
            dist=200000,
            extent=(-10, 35, 30, 60),
        )

        cells = repo.get_grid_cells(grid_def)
        cell = cells[0]

        assert cell.footprint.equals(cell.utm_footprint)
        assert cell.footprint.geom_type == "Polygon"
