from aer.grid import core
from shapely.geometry import Polygon
import geopandas as gpd


def test_grid_definition_init():
    grid = core.GridDefinition(d=10000)
    assert grid.D == 10000
    assert not grid.overlap


def test_generate_grid_cells():
    grid = core.GridDefinition(d=10000, overlap=False)
    # create a small polygon near equator
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])
    cells = grid.generate_grid_cells(polygon)
    assert len(cells) > 0
    # Every cell should intersect
    for cell in cells:
        assert cell.geom.intersects(polygon)
        assert cell.is_primary


def test_generate_grid_cells_overlap():
    grid = core.GridDefinition(d=10000, overlap=True)
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])
    cells = grid.generate_grid_cells(polygon)
    assert len(cells) > 0
    primary_cells = [c for c in cells if c.is_primary]
    overlap_cells = [c for c in cells if not c.is_primary]
    assert len(primary_cells) > 0
    assert len(overlap_cells) > 0


def test_cell_from_id():
    grid = core.GridDefinition(d=10000)
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])
    cells = grid.generate_grid_cells(polygon)
    first_cell_id = cells[0].id()

    reconstructed_cell = grid.cell_from_id(first_cell_id)
    assert reconstructed_cell.id() == first_cell_id
    # Test if geometry is reconstructed closely enough
    assert (
        reconstructed_cell.geom.intersection(cells[0].geom).area
        > 0.99 * cells[0].geom.area
    )


def test_grid_cell_to_geodataframe():
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(d=10000, geom=polygon, is_primary=True, cell_id="0U_0R")
    gdf = cell.to_geodataframe()
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 1
    assert gdf["grid_cell"].iloc[0] == "0U_0R"
    assert gdf["grid_dist"].iloc[0] == 10000
    assert "cell_geometry" in gdf.columns
    assert "cell_utm_crs" in gdf.columns


def test_get_cell_name():
    grid = core.GridDefinition(d=10000)
    name = grid.get_cell_name(
        row_idx=grid.row_count // 2 + 1, col_idx=60, lon_spacing=3.0, is_primary=True
    )
    assert "U" in name
    assert "OV" not in name

    name_ov = grid.get_cell_name(
        row_idx=grid.row_count // 2 + 1, col_idx=60, lon_spacing=3.0, is_primary=False
    )
    assert "OV" in name_ov


def test_grid_cell_area_name_and_def():
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(d=10000, geom=polygon, is_primary=True, cell_id="0U_0R")

    assert cell.area_name(50) == "0U_0R_dist-10000m_res-50m"
    area = cell.area_def(50)
    assert area.area_id == "0U_0R_dist-10000m_res-50m"
    assert area.width == 10000 // 50
    assert area.height == 10000 // 50


def test_to_esa_compatible_dataframe():
    grid = core.GridDefinition(d=10000)
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])
    cells = grid.generate_grid_cells(polygon)

    gdf = grid.to_esa_compatible_dataframe(cells)
    assert len(gdf) > 0
    assert "name" in gdf.columns
    assert "row" in gdf.columns
    assert "col" in gdf.columns
    assert "row_idx" in gdf.columns
    assert "col_idx" in gdf.columns
    assert "utm_zone" in gdf.columns
    assert "epsg" in gdf.columns
    assert gdf.crs == "EPSG:4326"
