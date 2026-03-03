import pytest
import pandas as pd
from shapely.geometry import Point, Polygon, GeometryCollection
from aer.spatial import Grid, get_utm_epsg_from_geometry, get_utm_zone_from_latlng


def test_get_utm_epsg_from_geometry_point():
    # Berlin (Northern Hemisphere)
    pt1 = Point(13.4050, 52.5200)
    epsg1 = get_utm_epsg_from_geometry(pt1)
    assert epsg1 == "32633"

    # Sydney (Southern Hemisphere)
    pt2 = Point(151.2093, -33.8688)
    epsg2 = get_utm_epsg_from_geometry(pt2)
    assert epsg2 == "32756"


def test_get_utm_epsg_from_geometry_polygon():
    # A small triangle near Berlin
    poly = Polygon([(13.0, 52.0), (13.5, 52.0), (13.5, 52.5)])
    epsg = get_utm_epsg_from_geometry(poly)
    assert epsg == "32633"


def test_get_utm_epsg_from_geometry_invalid_type():
    with pytest.raises(ValueError, match="Unsupported geometry type"):
        get_utm_epsg_from_geometry(GeometryCollection())


def test_get_utm_zone_from_latlng():
    # Berlin
    latlng = [52.5200, 13.4050]
    epsg = get_utm_zone_from_latlng(latlng)
    assert epsg == "32633"


def test_grid_initialization():
    grid = Grid(
        name="test_grid", dist=2000, latitude_range=(-30, 30), longitude_range=(-50, 50)
    )
    assert grid.name == "test_grid"
    assert grid.dist == 2000
    assert not grid.points.empty
    assert "cell_bounds" in grid.points.columns
    assert len(grid.rows) > 0


def test_grid_latlon2rowcol():
    grid = Grid(
        name="test_grid",
        dist=2000,
        latitude_range=(-80, 80),
        longitude_range=(-180, 180),
    )
    lats = [0, 45, -45]
    lons = [0, 10, -10]
    out = grid.latlon2rowcol(lats, lons)
    assert len(out[0]) == 3
    assert len(out[1]) == 3


def test_grid_rowcol2latlon():
    grid = Grid(
        name="test_grid",
        dist=2000,
        latitude_range=(-80, 80),
        longitude_range=(-180, 180),
    )
    lats = [0, 45, -45]
    lons = [0, 10, -10]
    out = grid.latlon2rowcol(lats, lons)
    row_back, col_back = grid.rowcol2latlon(out[0], out[1])
    assert len(row_back) == 3
    assert len(col_back) == 3


@pytest.mark.slow
def test_grid_matches_existing_100km():
    import geopandas as gpd
    from pathlib import Path

    # Generate the global 100km grid
    grid = Grid(name="global", dist=100)

    # Path to the existing grid
    current_file_dir = Path(__file__).parent
    spatial_dir = (
        current_file_dir.parent.parent.parent.parent / "components" / "aer" / "spatial"
    )
    existing_path = spatial_dir / "grid_global_100km.parquet"

    # Verify the file exists so we actually test against it
    assert existing_path.exists(), f"Could not find existing parquet at {existing_path}"

    # Load and reset indices
    existing_gdf = gpd.read_parquet(existing_path)
    new_gdf = grid.points.reset_index(drop=True)
    existing_gdf = existing_gdf.reset_index(drop=True)

    # Ensure types match. The original might not have 'cell_bounds' or some exact types could be slightly off but let's assert directly.
    # The default tolerance will apply for float geometries
    pd.testing.assert_frame_equal(
        new_gdf,
        existing_gdf,
        check_dtype=False,
    )
