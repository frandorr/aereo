from typing import cast

import geopandas as gpd
import pytest
from aereo.grid import core
from odc.geo.geobox import GeoBox
from shapely.geometry import Polygon, Point


def test_grid_definition_init():
    grid = core.GridDefinition(d=10000)
    assert grid.D == 10000
    assert not grid.overlap


def test_generate_raw_cells():
    grid = core.GridDefinition(d=10000, overlap=False)
    # create a small polygon near equator
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])
    cells = grid.generate_raw_cells(polygon)
    assert len(cells) > 0
    # Every cell should intersect
    for poly, cell_id, is_primary in cells:
        assert poly.intersects(polygon)
        assert is_primary


def test_generate_raw_cells_overlap():
    grid = core.GridDefinition(d=10000, overlap=True)
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])
    cells = grid.generate_raw_cells(polygon)
    assert len(cells) > 0
    primary_cells = [c for c in cells if c[2]]
    overlap_cells = [c for c in cells if not c[2]]
    assert len(primary_cells) > 0
    assert len(overlap_cells) > 0


def test_raw_cell_from_id():
    grid = core.GridDefinition(d=10000)
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])
    cells = grid.generate_raw_cells(polygon)
    first_poly, first_cell_id, _ = cells[0]

    recon_poly, recon_id, _ = grid.raw_cell_from_id(first_cell_id)
    assert recon_id == first_cell_id
    # Test if geometry is reconstructed closely enough
    assert recon_poly.intersection(first_poly).area > 0.99 * first_poly.area


def test_build_grid_cells():
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])

    cells = core.build_grid_cells(aoi=polygon, grid_dist=10_000)
    assert len(cells) > 0
    assert isinstance(cells[0], core.GridCell)
    assert cells[0].d == 10000

    gb = cells[0].to_geobox(resolution=50.0)
    assert isinstance(gb, GeoBox)


def test_grid_cell_to_geodataframe():
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(id="0U_0R", d=10000, cell_geometry=polygon)
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


def test_grid_cell_area_name_and_geobox():
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(id="0U_0R", d=10000, cell_geometry=polygon)

    assert cell.area_name(resolution=50.0) == "0U_0R_dist-10000m_res-50m"
    area = cell.to_geobox(resolution=50.0, margin=0.0)
    # With margin=0 the box is D x D metres (≈200 px at 50 m)
    assert area.shape.x == pytest.approx(10000 / 50, abs=1)
    assert area.shape.y == pytest.approx(10000 / 50, abs=1)


# --- GeoBox tests ---


def test_area_def_removed():
    """AreaDef should no longer exist in aereo.grid.core."""
    with pytest.raises(AttributeError):
        getattr(core, "AreaDef")


def test_geobox_returns_geobox():
    cell = core.GridCell(
        id="test", d=10000, cell_geometry=Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    )
    gb = cell.to_geobox(resolution=100.0, margin=0.0)
    assert isinstance(gb, GeoBox)
    assert gb.crs is not None
    assert gb.crs.to_epsg() == int(cell.utm_crs.split(":")[-1])


def test_geobox_fixed_shape_matches_d():
    polygon = Point(-64.0, -31.4).buffer(0.1)
    cells = core.build_grid_cells(aoi=polygon, grid_dist=100_000)
    gb = cells[0].to_geobox(resolution=2000.0)
    # GeoBox rounds to whole pixels; shape must be ≈ D / resolution
    assert gb.shape.x == pytest.approx(100_000 / 2000, abs=1)
    assert gb.shape.y == pytest.approx(100_000 / 2000, abs=1)


def test_geobox_from_generated_cell():
    """GeoBox from a real grid-generated cell should have valid extent and CRS."""
    polygon = Point(-64.0, -31.4).buffer(0.1)
    cells = core.build_grid_cells(aoi=polygon, grid_dist=100_000)
    assert len(cells) > 0
    ad = cells[0].to_geobox(resolution=2000.0)
    assert isinstance(ad, GeoBox)
    # With margin=0 the box is D x D metres (≈50 px at 2000 m)
    assert ad.shape.x == pytest.approx(100_000 / 2000, abs=1)
    assert ad.shape.y == pytest.approx(100_000 / 2000, abs=1)
    # Extent should have min < max for both x and y
    assert ad.extent.boundingbox.left < ad.extent.boundingbox.right
    assert ad.extent.boundingbox.bottom < ad.extent.boundingbox.top


def test_geobox_uses_fixed_size():
    """A cell's geobox extent should be a fixed D x D square, not natural bounds."""
    polygon = Point(-64.0, -31.4).buffer(0.1)
    cells = core.build_grid_cells(aoi=polygon, grid_dist=100_000)
    area = cells[0].to_geobox(resolution=2000.0)
    # The extent should be D x D metres (≈50 px), not derived from utm_footprint.bounds
    assert area.shape.x == pytest.approx(100_000 / 2000, abs=1)
    assert area.shape.y == pytest.approx(100_000 / 2000, abs=1)


def test_geobox_centered_on_grid_point():
    """geobox should be centred on the reprojected WGS84 centroid."""
    from aereo.spatial import reproject_geom

    polygon = Point(-64.0, -31.4).buffer(0.1)
    cells = core.build_grid_cells(aoi=polygon, grid_dist=100_000)
    gb = cells[0].to_geobox(resolution=2000.0)
    utm_centroid = cast(
        Point,
        reproject_geom(
            cells[0].cell_geometry.centroid,
            src_epsg="epsg:4326",
            dst_epsg=cells[0].utm_crs,
        ),
    )
    bbox = gb.boundingbox
    cx = (bbox.left + bbox.right) / 2
    cy = (bbox.bottom + bbox.top) / 2
    assert cx == pytest.approx(utm_centroid.x, abs=2000)
    assert cy == pytest.approx(utm_centroid.y, abs=2000)


def test_geobox_with_margin():
    """margin should expand the box beyond D x D."""
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(id="0U_0R", d=10000, cell_geometry=polygon)
    gb_no_margin = cell.to_geobox(resolution=50.0, margin=0.0)
    gb_with_margin = cell.to_geobox(resolution=50.0, margin=6.8)
    assert gb_with_margin.shape.x > gb_no_margin.shape.x
    assert gb_with_margin.shape.y > gb_no_margin.shape.y


def test_geobox_origin_independent_of_resolution():
    """GeoBoxes for the same cell at different resolutions share the same origin.

    This guarantees that independent extractions of the same cell (e.g. GOES at
    2 km and VIIRS at 400 m) produce aligned pixel grids when the resolutions
    are integer multiples of each other. The finer resolution is aligned to the
    coarser one so the pixel edges match.
    """
    polygon = Point(-64.0, -31.4).buffer(0.1)
    cells = core.build_grid_cells(aoi=polygon, grid_dist=100_000)
    cell = cells[0]
    gb_400m = cell.to_geobox(resolution=400.0, alignment_resolution=2000.0)
    gb_2km = cell.to_geobox(resolution=2000.0, alignment_resolution=2000.0)

    assert gb_400m.extent.boundingbox.left == pytest.approx(
        gb_2km.extent.boundingbox.left
    )
    assert gb_400m.extent.boundingbox.top == pytest.approx(
        gb_2km.extent.boundingbox.top
    )


def test_geobox_origin_independent_of_resolution_with_margin():
    """Alignment is preserved even when a margin expands the box."""
    polygon = Point(-64.0, -31.4).buffer(0.1)
    cells = core.build_grid_cells(aoi=polygon, grid_dist=100_000)
    cell = cells[0]
    gb_400m = cell.to_geobox(resolution=400.0, margin=10.0, alignment_resolution=2000.0)
    gb_2km = cell.to_geobox(resolution=2000.0, margin=10.0, alignment_resolution=2000.0)

    assert gb_400m.extent.boundingbox.left == pytest.approx(
        gb_2km.extent.boundingbox.left
    )
    assert gb_400m.extent.boundingbox.top == pytest.approx(
        gb_2km.extent.boundingbox.top
    )
    # The finer grid should be an exact refinement of the coarser one.
    assert gb_400m.shape.x == gb_2km.shape.x * 5
    assert gb_400m.shape.y == gb_2km.shape.y * 5


# --- cells_bounds tests ---


def test_cells_bounds_empty_raises():
    with pytest.raises(ValueError, match="At least one GridCell is required"):
        core.cells_bounds([])


def test_cells_bounds_single_cell():
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])
    cell = core.GridCell(id="0U_0R", d=10000, cell_geometry=polygon)

    bounds = core.cells_bounds([cell])
    assert bounds == pytest.approx(polygon.bounds, abs=1e-9)


def test_cells_bounds_multiple_cells():
    polygon = Polygon([[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]])
    cells = core.build_grid_cells(aoi=polygon, grid_dist=10_000)
    assert len(cells) > 1

    bounds = core.cells_bounds(cells)
    minx, miny, maxx, maxy = bounds

    # Bounds should exactly match the union of all cell bounds.
    expected_minx = min(cell.cell_geometry.bounds[0] for cell in cells)
    expected_miny = min(cell.cell_geometry.bounds[1] for cell in cells)
    expected_maxx = max(cell.cell_geometry.bounds[2] for cell in cells)
    expected_maxy = max(cell.cell_geometry.bounds[3] for cell in cells)
    assert minx == pytest.approx(expected_minx, abs=1e-9)
    assert miny == pytest.approx(expected_miny, abs=1e-9)
    assert maxx == pytest.approx(expected_maxx, abs=1e-9)
    assert maxy == pytest.approx(expected_maxy, abs=1e-9)


def test_cells_bounds_with_buffer_expands():
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])
    cells = core.build_grid_cells(aoi=polygon, grid_dist=10_000)
    assert len(cells) > 0

    base_bounds = core.cells_bounds(cells)
    buffered_bounds = core.cells_bounds(cells, buffer_m=1000.0)

    assert buffered_bounds[0] < base_bounds[0]
    assert buffered_bounds[1] < base_bounds[1]
    assert buffered_bounds[2] > base_bounds[2]
    assert buffered_bounds[3] > base_bounds[3]


def test_cells_bounds_buffer_approximate_size():
    """Buffer expansion near the equator should be close to the requested metres."""
    polygon = Polygon([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]])
    cells = core.build_grid_cells(aoi=polygon, grid_dist=10_000)
    assert len(cells) > 0

    buffer_m = 1000.0
    base_bounds = core.cells_bounds(cells)
    buffered_bounds = core.cells_bounds(cells, buffer_m=buffer_m)

    # At the equator 1 degree ≈ 111,320 m, so 1000 m ≈ 0.009 degrees.
    # Allow generous tolerance because buffering is done in UTM and reprojected.
    expansion_x = (buffered_bounds[2] - buffered_bounds[0]) - (
        base_bounds[2] - base_bounds[0]
    )
    expansion_y = (buffered_bounds[3] - buffered_bounds[1]) - (
        base_bounds[3] - base_bounds[1]
    )

    expected_deg = buffer_m / 111_320
    assert expansion_x == pytest.approx(2 * expected_deg, abs=0.01)
    assert expansion_y == pytest.approx(2 * expected_deg, abs=0.01)


def test_cells_bounds_exported_from_module():
    from aereo.grid import cells_bounds

    assert callable(cells_bounds)


# --- Non-integer / sub-metre resolution tests ---


def test_geobox_sub_metre_resolution():
    """Sub-metre resolutions should not trigger ZeroDivisionError."""
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(id="0U_0R", d=1000, cell_geometry=polygon)

    gb = cell.to_geobox(resolution=0.3)
    assert isinstance(gb, GeoBox)
    # Width must be at least the nominal cell size.
    assert gb.shape.x * 0.3 >= 1000
    assert gb.shape.y * 0.3 >= 1000


def test_geobox_modis_like_resolution():
    """Non-integer-metre resolutions such as MODIS (~231.656 m) must work."""
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(id="0U_0R", d=10000, cell_geometry=polygon)

    modis_res = 231.656358325958
    gb = cell.to_geobox(resolution=modis_res)
    assert isinstance(gb, GeoBox)
    assert gb.shape.x * modis_res >= 10000
    assert gb.shape.y * modis_res >= 10000


def test_geobox_incommensurate_alignment_raises():
    """Alignment resolutions that are not integer multiples of the target raise."""
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(id="0U_0R", d=10000, cell_geometry=polygon)

    with pytest.raises(ValueError, match="integer multiples"):
        cell.to_geobox(resolution=400.0, alignment_resolution=1500.0)


def test_geobox_non_positive_resolution_raises():
    """Zero or negative resolutions are rejected."""
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(id="0U_0R", d=10000, cell_geometry=polygon)

    with pytest.raises(ValueError, match="resolution must be positive"):
        cell.to_geobox(resolution=0.0)

    with pytest.raises(ValueError, match="resolution must be positive"):
        cell.to_geobox(resolution=-10.0)

    with pytest.raises(ValueError, match="alignment_resolution must be positive"):
        cell.to_geobox(resolution=10.0, alignment_resolution=-10.0)


def test_geobox_alignment_preserves_sub_metre_origin():
    """Nested sub-metre resolutions with a commensurate alignment share an origin."""
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    cell = core.GridCell(id="0U_0R", d=1000, cell_geometry=polygon)

    gb_fine = cell.to_geobox(resolution=0.1, alignment_resolution=0.5)
    gb_coarse = cell.to_geobox(resolution=0.5, alignment_resolution=0.5)

    assert gb_fine.extent.boundingbox.left == pytest.approx(
        gb_coarse.extent.boundingbox.left
    )
    assert gb_fine.extent.boundingbox.top == pytest.approx(
        gb_coarse.extent.boundingbox.top
    )
    assert gb_fine.shape.x == gb_coarse.shape.x * 5
    assert gb_fine.shape.y == gb_coarse.shape.y * 5
