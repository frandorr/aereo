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
    # width/height should reflect natural UTM footprint bounds, not self.D
    bounds = cell.utm_footprint.bounds
    expected_width = round((bounds[2] - bounds[0]) / 50)
    expected_height = round((bounds[3] - bounds[1]) / 50)
    assert area.width == expected_width
    assert area.height == expected_height


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


# --- AreaDef tests ---


def test_area_def_is_frozen():
    """AreaDef must be immutable (attrs.frozen)."""
    ad = core.AreaDef(
        area_id="test",
        description="test area",
        projection="EPSG:32720",
        width=50,
        height=50,
        area_extent=(0.0, 0.0, 100000.0, 100000.0),
    )
    import attrs
    import pytest

    with pytest.raises(attrs.exceptions.FrozenInstanceError):
        ad.area_id = "changed"  # type: ignore[misc]


def test_area_def_to_yaml_structure():
    """to_yaml() must produce valid YAML with all required pyresample keys."""
    ad = core.AreaDef(
        area_id="cell_1",
        description="Area defined for cell_1 in EPSG:32720",
        projection="EPSG:32720",
        width=50,
        height=50,
        area_extent=(500000.0, 6000000.0, 600000.0, 6100000.0),
    )
    yaml_str = ad.to_yaml()
    assert "cell_1:" in yaml_str
    assert "EPSG: 32720" in yaml_str
    assert "height: 50" in yaml_str
    assert "width: 50" in yaml_str
    assert "lower_left_xy: [500000.0, 6000000.0]" in yaml_str
    assert "upper_right_xy: [600000.0, 6100000.0]" in yaml_str
    assert "units: m" in yaml_str


def test_area_def_returns_area_def_type():
    """GridCell.area_def() must return an AreaDef instance."""
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(d=100000, geom=polygon, is_primary=True, cell_id="0U_0R")
    ad = cell.area_def(2000)
    assert isinstance(ad, core.AreaDef)
    # width/height should reflect natural UTM footprint bounds, not self.D
    bounds = cell.utm_footprint.bounds
    expected_width = round((bounds[2] - bounds[0]) / 2000)
    expected_height = round((bounds[3] - bounds[1]) / 2000)
    assert ad.width == expected_width
    assert ad.height == expected_height
    # projection can be "EPSG:32631" or just "32631"
    epsg_code = ad.projection.split(":")[-1] if ":" in ad.projection else ad.projection
    assert epsg_code.isdigit()


def test_area_def_from_generated_cell():
    """AreaDef from a real grid-generated cell should have valid extent and CRS."""
    from shapely.geometry import Point

    grid = core.GridDefinition(d=100000)
    cells = grid.generate_grid_cells(Point(-64.0, -31.4).buffer(0.1))
    assert len(cells) > 0
    ad = cells[0].area_def(2000)
    assert isinstance(ad, core.AreaDef)
    # width/height should reflect natural UTM footprint bounds, not self.D
    bounds = cells[0].utm_footprint.bounds
    expected_width = round((bounds[2] - bounds[0]) / 2000)
    expected_height = round((bounds[3] - bounds[1]) / 2000)
    assert ad.width == expected_width
    assert ad.height == expected_height
    # Extent should have min < max for both x and y
    assert ad.area_extent[0] < ad.area_extent[2]
    assert ad.area_extent[1] < ad.area_extent[3]


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
    assert area.width == expected_width
    assert area.height == expected_height


def test_area_def_conform_to():
    """When conform_to is given, width/height should match target + padding."""
    cell = core.GridCell(
        d=10000, geom=Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]), cell_id="test"
    )
    area = cell.area_def(100, padding=1, conform_to=(50, 60))
    assert area.width == 52  # 50 + 2*1
    assert area.height == 62  # 60 + 2*1


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
        assert area.width == max_w
        assert area.height == max_h


def test_max_shape_with_padding():
    """Padding should be accounted for in max_shape."""
    grid = core.GridDefinition(d=10_000)
    polygon = Polygon([[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]])
    cells = grid.generate_grid_cells(polygon)
    max_w_padded, max_h_padded = grid.max_shape(cells, resolution=100, padding=2)
    max_w, max_h = grid.max_shape(cells, resolution=100, padding=0)
    assert max_w_padded == max_w + 4
    assert max_h_padded == max_h + 4


def test_area_def_yaml_round_trip_with_pyresample():
    """to_yaml() output must be loadable by pyresample.area_config.load_area_from_string."""
    try:
        from pyresample.area_config import load_area_from_string
    except ImportError:
        import pytest

        pytest.skip("pyresample not installed")

    ad = core.AreaDef(
        area_id="test_roundtrip",
        description="Round-trip test area in EPSG:32720",
        projection="EPSG:32720",
        width=50,
        height=50,
        area_extent=(500000.0, 6000000.0, 600000.0, 6100000.0),
    )
    area = load_area_from_string(ad.to_yaml(), ad.area_id)
    assert area is not None and not isinstance(area, list)
    assert area.width == ad.width
    assert area.height == ad.height
    assert area.area_extent == ad.area_extent
