import geopandas as gpd
import pytest
from aer.grid import core
from odc.geo.geobox import GeoBox
from shapely.geometry import Polygon


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
    # width/height should reflect natural UTM footprint bounds, not self.D
    bounds = cell.utm_footprint.bounds
    expected_width = round((bounds[2] - bounds[0]) / 50)
    expected_height = round((bounds[3] - bounds[1]) / 50)
    assert area.shape.x >= expected_width
    assert area.shape.y >= expected_height


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


# --- GeoBox tests ---


def test_area_def_removed():
    """AreaDef should no longer exist in aer.grid.core."""
    with pytest.raises(AttributeError):
        getattr(core, "AreaDef")


def test_area_def_returns_geobox():
    cell = core.GridCell(
        d=10000, geom=Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]), cell_id="test"
    )
    gb = cell.area_def(100)
    assert isinstance(gb, GeoBox)
    assert gb.crs is not None
    assert gb.crs.to_epsg() == int(cell.utm_crs.split(":")[-1])


def test_area_def_natural_shape_matches_utm_footprint():
    from shapely.geometry import Point

    grid = core.GridDefinition(d=100_000)
    cells = grid.generate_grid_cells(Point(-64.0, -31.4).buffer(0.1))
    cell = cells[0]
    gb = cell.area_def(2000)
    bounds = cell.utm_footprint.bounds
    # GeoBox rounds up to whole pixels; shape must be >= natural
    assert gb.shape.x >= round((bounds[2] - bounds[0]) / 2000)
    assert gb.shape.y >= round((bounds[3] - bounds[1]) / 2000)


def test_area_def_from_generated_cell():
    """GeoBox from a real grid-generated cell should have valid extent and CRS."""
    from shapely.geometry import Point

    grid = core.GridDefinition(d=100000)
    cells = grid.generate_grid_cells(Point(-64.0, -31.4).buffer(0.1))
    assert len(cells) > 0
    ad = cells[0].area_def(2000)
    assert isinstance(ad, GeoBox)
    # width/height should reflect natural UTM footprint bounds, not self.D
    bounds = cells[0].utm_footprint.bounds
    expected_width = round((bounds[2] - bounds[0]) / 2000)
    expected_height = round((bounds[3] - bounds[1]) / 2000)
    assert ad.shape.x >= expected_width
    assert ad.shape.y >= expected_height
    # Extent should have min < max for both x and y
    assert ad.extent.boundingbox.left < ad.extent.boundingbox.right
    assert ad.extent.boundingbox.bottom < ad.extent.boundingbox.top


def test_area_def_uses_natural_bounds():
    """A cell's area_def extent should match its utm_footprint, not self.D."""
    from shapely.geometry import Point

    grid = core.GridDefinition(d=100_000)
    cells = grid.generate_grid_cells(Point(-64.0, -31.4).buffer(0.1))
    cell = cells[0]
    area = cell.area_def(2000)
    # The extent should be derived from utm_footprint.bounds, not from D=100_000
    bounds = cell.utm_footprint.bounds
    expected_width = round((bounds[2] - bounds[0]) / 2000)
    expected_height = round((bounds[3] - bounds[1]) / 2000)
    assert area.shape.x >= expected_width
    assert area.shape.y >= expected_height


def test_area_def_conform_to():
    """When conform_to is given, width/height should match target + padding."""
    cell = core.GridCell(
        d=10000, geom=Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]), cell_id="test"
    )
    area = cell.area_def(100, padding=1, conform_to=(50, 60))
    assert area.shape.x == 52  # 50 + 2*1
    assert area.shape.y == 62  # 60 + 2*1


def test_area_def_geobox_kwargs():
    cell = core.GridCell(
        d=10000, geom=Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]), cell_id="test"
    )
    gb_edge = cell.area_def(100, anchor="edge")
    gb_tight = cell.area_def(100, tight=True)
    # tight=True disables pixel snapping, so extent can differ from edge-aligned.
    assert gb_edge.shape == gb_tight.shape  # for this evenly-divisible test case
    assert gb_edge.extent != gb_tight.extent


def test_max_shape_across_cells():
    """max_shape should return the maximum natural pixel dimensions across cells."""
    grid = core.GridDefinition(d=10_000)
    polygon = Polygon([[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]])
    cells = grid.generate_grid_cells(polygon)
    max_w, max_h = grid.max_shape(cells, resolution=100)
    assert max_w > 0
    assert max_h > 0
    # Every cell should fit inside max_shape when padded to it
    for cell in cells:
        area = cell.area_def(100, conform_to=(max_w, max_h))
        assert area.shape.x == max_w
        assert area.shape.y == max_h


def test_max_shape_with_padding():
    """Padding should be accounted for in max_shape."""
    grid = core.GridDefinition(d=10_000)
    polygon = Polygon([[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]])
    cells = grid.generate_grid_cells(polygon)
    max_w_padded, max_h_padded = grid.max_shape(cells, resolution=100, padding=2)
    max_w, max_h = grid.max_shape(cells, resolution=100, padding=0)
    assert max_w_padded == max_w + 4
    assert max_h_padded == max_h + 4
