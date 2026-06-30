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

    patches = core.build_grid_cells(aoi=polygon, grid_dist=10_000, resolution=50.0)
    assert len(patches) > 0
    assert isinstance(patches[0], core.ExtractionPatch)
    assert patches[0].resolution == 50.0
    assert patches[0].d == 10000


def test_extraction_patch_to_geodataframe():
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    patch = core.ExtractionPatch(
        id="0U_0R",
        d=10000,
        cell_geometry=polygon,
        resolution=10.0,
        margin=0.0,
        padding=0,
    )
    gdf = patch.to_geodataframe()
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


def test_extraction_patch_area_name_and_geobox():
    polygon = Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    patch = core.ExtractionPatch(
        id="0U_0R",
        d=10000,
        cell_geometry=polygon,
        resolution=50.0,
        margin=0.0,
        padding=0,
    )

    assert patch.area_name() == "0U_0R_dist-10000m_res-50m"
    area = patch.geobox
    # With margin=0 the box is D x D metres (≈200 px at 50 m)
    assert area.shape.x == pytest.approx(10000 / 50, abs=1)
    assert area.shape.y == pytest.approx(10000 / 50, abs=1)


# --- GeoBox tests ---


def test_area_def_removed():
    """AreaDef should no longer exist in aereo.grid.core."""
    with pytest.raises(AttributeError):
        getattr(core, "AreaDef")


def test_geobox_returns_geobox():
    patch = core.ExtractionPatch(
        id="test",
        d=10000,
        cell_geometry=Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
        resolution=100.0,
        margin=0.0,
        padding=0,
    )
    gb = patch.geobox
    assert isinstance(gb, GeoBox)
    assert gb.crs is not None
    assert gb.crs.to_epsg() == int(patch.utm_crs.split(":")[-1])


def test_geobox_fixed_shape_matches_d():
    polygon = Point(-64.0, -31.4).buffer(0.1)
    patches = core.build_grid_cells(aoi=polygon, grid_dist=100_000, resolution=2000.0)
    patch = patches[0]
    gb = patch.geobox
    # GeoBox rounds to whole pixels; shape must be ≈ D / resolution
    assert gb.shape.x == pytest.approx(100_000 / 2000, abs=1)
    assert gb.shape.y == pytest.approx(100_000 / 2000, abs=1)


def test_geobox_from_generated_patch():
    """GeoBox from a real grid-generated patch should have valid extent and CRS."""
    polygon = Point(-64.0, -31.4).buffer(0.1)
    patches = core.build_grid_cells(aoi=polygon, grid_dist=100_000, resolution=2000.0)
    assert len(patches) > 0
    ad = patches[0].geobox
    assert isinstance(ad, GeoBox)
    # With margin=0 the box is D x D metres (≈50 px at 2000 m)
    assert ad.shape.x == pytest.approx(100_000 / 2000, abs=1)
    assert ad.shape.y == pytest.approx(100_000 / 2000, abs=1)
    # Extent should have min < max for both x and y
    assert ad.extent.boundingbox.left < ad.extent.boundingbox.right
    assert ad.extent.boundingbox.bottom < ad.extent.boundingbox.top


def test_geobox_uses_fixed_size():
    """A patch's geobox extent should be a fixed D x D square, not natural bounds."""
    polygon = Point(-64.0, -31.4).buffer(0.1)
    patches = core.build_grid_cells(aoi=polygon, grid_dist=100_000, resolution=2000.0)
    patch = patches[0]
    area = patch.geobox
    # The extent should be D x D metres (≈50 px), not derived from utm_footprint.bounds
    assert area.shape.x == pytest.approx(100_000 / 2000, abs=1)
    assert area.shape.y == pytest.approx(100_000 / 2000, abs=1)


def test_geobox_conform_to():
    """When conform_to is given, width/height should match target + padding."""
    patch = core.ExtractionPatch(
        id="test",
        d=10000,
        cell_geometry=Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
        resolution=100.0,
        margin=0.0,
        padding=1,
        conform_to=(50, 60),
    )
    area = patch.geobox
    assert area.shape.x == 52  # 50 + 2*1
    assert area.shape.y == 62  # 60 + 2*1


def test_geobox_centered_on_grid_point():
    """geobox should be centred on the reprojected WGS84 centroid."""
    from aereo.spatial import reproject_geom

    polygon = Point(-64.0, -31.4).buffer(0.1)
    patches = core.build_grid_cells(aoi=polygon, grid_dist=100_000, resolution=2000.0)
    patch = patches[0]
    gb = patch.geobox
    utm_centroid = cast(
        Point,
        reproject_geom(
            patch.cell_geometry.centroid, src_epsg="epsg:4326", dst_epsg=patch.utm_crs
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
    patch_no_margin = core.ExtractionPatch(
        id="0U_0R",
        d=10000,
        cell_geometry=polygon,
        resolution=50.0,
        margin=0.0,
        padding=0,
    )
    patch_with_margin = core.ExtractionPatch(
        id="0U_0R",
        d=10000,
        cell_geometry=polygon,
        resolution=50.0,
        margin=6.8,
        padding=0,
    )
    gb_no_margin = patch_no_margin.geobox
    gb_with_margin = patch_with_margin.geobox
    assert gb_with_margin.shape.x > gb_no_margin.shape.x
    assert gb_with_margin.shape.y > gb_no_margin.shape.y
