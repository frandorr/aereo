from datetime import datetime
import geopandas as gpd
from shapely.geometry import Point, Polygon
from aer.search.core import SearchResult, SearchResultSchema


def test_search_result_conversion_roundtrip() -> None:
    """Test converting between SearchResult GDF and objects."""

    # Create mock GDF
    data = {
        "unique_id": ["U1", "U2"],
        "product_id": ["P1", "P2"],
        "granule_id": ["G1", "G2"],
        "start_time": [datetime(2025, 1, 1), datetime(2025, 1, 2)],
        "end_time": [datetime(2025, 1, 3), datetime(2025, 1, 4)],
        "overlap_mode": ["contains", "contains"],
        "name": ["10U_20R", "11U_21R"],
        "row": ["10U", "11U"],
        "col": ["20R", "21R"],
        "utm_zone": ["31N", "31N"],
        "epsg": ["EPSG:32631", "EPSG:32631"],
        "dist": [100, 100],
        "cell_bounds": [
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            Polygon([(1, 1), (2, 1), (2, 2), (1, 2)]),
        ],
        "channel": [None, None],
    }
    # Pandera needs geometry column
    gdf = gpd.GeoDataFrame(data, geometry=[Point(0.5, 0.5), Point(1.5, 1.5)])

    # 1. GDF -> List[SearchResult]
    results = SearchResult.from_gdf(gdf)
    assert len(results) == 2
    assert isinstance(results[0], SearchResult)
    assert results[0].unique_id == "U1"
    assert results[1].granule_id == "G2"

    # 2. List[SearchResult] -> GDF
    gdf_new = SearchResult.to_gdf(results)
    assert len(gdf_new) == 2
    assert "unique_id" in gdf_new.columns
    assert gdf_new.iloc[0]["unique_id"] == "U1"
    assert gdf_new.iloc[1]["granule_id"] == "G2"

    # Validate it passes schema
    SearchResultSchema.validate(gdf_new)
