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
    data = {
        "product_name": ["GOES-ABI-L2-CMIP"],
        "granule_id": ["G16_s20250101_e20250102"],
        "start_time": [datetime(2025, 1, 1)],
        "end_time": [datetime(2025, 1, 2)],
        "s3_url": ["s3://noaa-goes16/test.nc"],
        "https_url": [None],
        "size_mb": [42.0],
        "geometry": [Point(-75.0, 40.0)],
        "overlapping_spatial_extent": [None],
        "input_spatial_extent": [None],
        "cell_overlap_mode": ["contains"],
    }
    return gpd.GeoDataFrame(data, geometry="geometry")


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
    assert validated.iloc[0]["product_name"] == "GOES-ABI-L2-CMIP"
    assert validated.iloc[0]["granule_id"] == "G16_s20250101_e20250102"


def test_extract_empty_gdf() -> None:
    """Extract on empty (but schema-valid) GeoDataFrame returns empty result."""
    empty_gdf = gpd.GeoDataFrame(
        {
            "product_name": pd.Series([], dtype="str"),
            "granule_id": pd.Series([], dtype="str"),
            "start_time": pd.Series([], dtype="datetime64[ns]"),
            "end_time": pd.Series([], dtype="datetime64[ns]"),
            "s3_url": pd.Series([], dtype="str"),
            "https_url": pd.Series([], dtype="str"),
            "size_mb": pd.Series([], dtype="float"),
            "geometry": gpd.GeoSeries([], dtype="geometry"),
            "overlapping_spatial_extent": pd.Series([], dtype="object"),
            "input_spatial_extent": pd.Series([], dtype="object"),
            "cell_overlap_mode": pd.Series([], dtype="str"),
        },
        geometry="geometry",
    )

    extracted = run_extract("dummy-extract", empty_gdf, "/tmp/empty")
    assert len(extracted) == 0
    assert "reprojected_path" in extracted.columns
    assert "resolution" in extracted.columns
