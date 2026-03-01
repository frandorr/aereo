import earthaccess
import pandas as pd
from typing import Any
from shapely.geometry import Polygon
from shapely.ops import unary_union

from aer.temporal import TimeRange
from aer.spectral import Product
from aer.spatial import GridSpatialExtent


def _parse_umm_polygon(umm_data: dict[str, Any]) -> Polygon:
    """Helper to extract a Shapely Polygon representing the data extent from CMR UMM meta."""
    spatial = umm_data.get("SpatialExtent", {})
    horizontal = spatial.get("HorizontalSpatialDomain", {})
    geometry = horizontal.get("Geometry", {})

    # Try BoundingRectangles (many polar products use this)
    bboxes = geometry.get("BoundingRectangles", [])
    if bboxes:
        bbox = bboxes[0]
        # Bounding coordinates
        w = bbox.get("WestBoundingCoordinate", 0)
        s = bbox.get("SouthBoundingCoordinate", 0)
        e = bbox.get("EastBoundingCoordinate", 0)
        n = bbox.get("NorthBoundingCoordinate", 0)
        return Polygon([(w, s), (e, s), (e, n), (w, n), (w, s)])

    # Try Polygons (products with complex footprints)
    polygons = geometry.get("Polygons", [])
    if polygons:
        boundary = polygons[0].get("Boundary", {})
        points = boundary.get("Points", [])
        if points:
            coords = [(p.get("Longitude", 0), p.get("Latitude", 0)) for p in points]
            return Polygon(coords)

    # Fallback to an empty polygon if CMR is missing spatial info
    return Polygon()


def search_earthaccess(
    products: list[Product],
    time_range: TimeRange,
    spatial_extent: GridSpatialExtent | None = None,
    **kwargs: Any,
) -> pd.DataFrame:
    """
    Search for earthaccess data given a list of Products, a TimeRange, and an optional GridSpatialExtent.
    Returns a pandas DataFrame with the search results.

    Args:
        products: A list of spectral Products to search for (uses product.name).
        time_range: The TimeRange representing start and end time.
        spatial_extent: An optional GridSpatialExtent. If provided, filters CMR by its
                        overall bounding box, and checks each returned granule to see
                        which cells are fully contained within it.
        **kwargs: Additional parameters passed directly to earthaccess.search_data.

    Returns:
        A pd.DataFrame containing product name, start time, end time, s3 urls, sizes,
        and optionally a 'grid_cells' column listing cell IDs fully contained by each file.
    """
    temporal = (
        time_range.start.strftime("%Y-%m-%d %H:%M:%S"),
        time_range.end.strftime("%Y-%m-%d %H:%M:%S"),
    )

    short_names = [p.name for p in products]

    # Apply bounding box filter if spatial_extent is provided
    if spatial_extent and spatial_extent.grid_cells:
        # Aggregate all cell bounds to find the maximum WGS84 bounding box
        all_bounds = unary_union([cell.bounds for cell in spatial_extent.grid_cells])
        minx, miny, maxx, maxy = all_bounds.bounds
        kwargs["bounding_box"] = (minx, miny, maxx, maxy)

    results = earthaccess.search_data(
        short_name=short_names, temporal=temporal, **kwargs
    )

    columns = [
        "product_name",
        "granule_id",
        "concept_id",
        "start_time",
        "end_time",
        "s3_url",
        "https_url",
        "size_mb",
    ]
    if spatial_extent:
        columns.append("grid_cells")

    if not results:
        return pd.DataFrame(columns=columns)

    rows = []
    for granule in results:
        meta = granule.get("meta", {})
        umm = granule.get("umm", {})

        # Get data links
        direct_links = granule.data_links(access="direct")
        external_links = granule.data_links(access="external")

        s3_url = direct_links[0] if direct_links else None
        https_url = external_links[0] if external_links else None

        # Temporal extents
        temporal_ext = umm.get("TemporalExtent", {})
        range_dt = temporal_ext.get("RangeDateTime", {})
        start_time = range_dt.get("BeginningDateTime")
        end_time = range_dt.get("EndingDateTime")

        # Determine exact product name from UMM metadata
        coll_ref = umm.get("CollectionReference", {})
        extracted_product_name = coll_ref.get("ShortName")

        row_data = {
            "product_name": extracted_product_name,
            "granule_id": meta.get("native-id"),
            "concept_id": meta.get("concept-id"),
            "start_time": pd.to_datetime(start_time) if start_time else None,
            "end_time": pd.to_datetime(end_time) if end_time else None,
            "s3_url": s3_url,
            "https_url": https_url,
            "size_mb": granule.size(),
        }

        # Check containment against cells if a spatial extent was requested
        if spatial_extent:
            granule_poly = _parse_umm_polygon(umm)

            contained_cells = []
            for cell in spatial_extent.grid_cells:
                # The user requested explicit cell IDs fully contained inside the asset.
                # If you need intersecting rather than fully contained later, change to .intersects()
                if granule_poly.contains(cell.bounds):
                    contained_cells.append(f"{cell.row}_{cell.col}")

            row_data["grid_cells"] = contained_cells

        rows.append(row_data)

    return pd.DataFrame(rows)
