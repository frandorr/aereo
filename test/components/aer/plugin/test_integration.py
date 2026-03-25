"""Integration test: dummy search + extract plugins exercising the full flow."""

from datetime import datetime
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from aer.extract.core import ExtractedResultSchema
from aer.plugin import plugin, run_extract, run_search


# ---------------------------------------------------------------------------
# Dummy plugins (registered at import time via @plugin)
# ---------------------------------------------------------------------------


@plugin(name="dummy-search", category="search")
def _dummy_search(query: Any, **kwargs: Any) -> gpd.GeoDataFrame:
    """Return a minimal SearchResultSchema-compliant GeoDataFrame."""
    from shapely.geometry import Polygon

    test_geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    data = {
        "unique_id": ["U1"],
        "product_id": ["GOES-ABI-L2-CMIP"],
        "granule_id": ["G16_s20250101_e20250102"],
        "start_time": [datetime(2025, 1, 1)],
        "end_time": [datetime(2025, 1, 2)],
        "s3_url": ["s3://noaa-goes16/test.nc"],
        "https_url": [None],
        "size_mb": [42.0],
        "name": ["10U_20R"],
        "row": ["10U"],
        "col": ["20R"],
        "row_idx": [0],
        "col_idx": [0],
        "utm_zone": ["31N"],
        "epsg": ["EPSG:32615"],
        "dist": [100],
        "cell_bounds": [test_geom],
        "channel": ["C01"],
        "overlap_mode": ["contains"],
    }
    return gpd.GeoDataFrame(data, geometry=[Point(-75.0, 40.0)])


@plugin(name="dummy-extract", category="extract")
def _dummy_extract(
    gdf: gpd.GeoDataFrame,
    output_dir: str,
    **kwargs: Any,
) -> gpd.GeoDataFrame:
    """Transform search results into ExtractedResultSchema by adding extract columns."""
    result = gdf.copy()
    result["reprojected_path"] = [
        f"{output_dir}/{gid}.tif" for gid in result["granule_id"]
    ]
    result["resolution"] = 2000.0
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_search_then_extract_integration() -> None:
    """Full flow: run_search → run_extract → schema validation."""
    # Search
    search_results = run_search("dummy-search", {"products": ["GOES"]})
    assert len(search_results) == 1
    assert "granule_id" in search_results.columns

    # Extract
    extracted = run_extract("dummy-extract", search_results, "/tmp/test_output")
    assert len(extracted) == 1

    # Validate against schema
    validated = ExtractedResultSchema.validate(extracted)
    assert "reprojected_path" in validated.columns
    assert "resolution" in validated.columns
    assert (
        validated.iloc[0]["reprojected_path"]
        == "/tmp/test_output/G16_s20250101_e20250102.tif"
    )
    assert validated.iloc[0]["resolution"] == 2000.0

    # Original search columns preserved
    assert validated.iloc[0]["product_id"] == "GOES-ABI-L2-CMIP"
    assert validated.iloc[0]["granule_id"] == "G16_s20250101_e20250102"


def test_extract_empty_gdf() -> None:
    """Extract on empty (but schema-valid) GeoDataFrame returns empty result."""
    empty_gdf = gpd.GeoDataFrame(
        {
            "unique_id": pd.Series([], dtype="str"),
            "product_id": pd.Series([], dtype="str"),
            "granule_id": pd.Series([], dtype="str"),
            "start_time": pd.Series([], dtype="datetime64[ns]"),
            "end_time": pd.Series([], dtype="datetime64[ns]"),
            "s3_url": pd.Series([], dtype="str"),
            "https_url": pd.Series([], dtype="str"),
            "size_mb": pd.Series([], dtype="float"),
            "name": pd.Series([], dtype="str"),
            "row": pd.Series([], dtype="str"),
            "col": pd.Series([], dtype="str"),
            "row_idx": pd.Series([], dtype="int64"),
            "col_idx": pd.Series([], dtype="int64"),
            "utm_zone": pd.Series([], dtype="str"),
            "epsg": pd.Series([], dtype="str"),
            "dist": pd.Series([], dtype="int64"),
            "cell_bounds": gpd.GeoSeries([], dtype="geometry"),
            "channel": pd.Series([], dtype="str"),
            "overlap_mode": pd.Series([], dtype="str"),
        },
        geometry=gpd.GeoSeries([], dtype="geometry"),
    )

    extracted = run_extract("dummy-extract", empty_gdf, "/tmp/empty")
    assert len(extracted) == 0
    assert "reprojected_path" in extracted.columns
    assert "resolution" in extracted.columns
