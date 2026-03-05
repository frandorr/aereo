from typing import Any

import earthaccess
import geopandas as gpd
import pandas as pd
from returns import result
from shapely.geometry import Polygon
from shapely.ops import unary_union
from structlog import get_logger

from aer.plugin import plugin
from aer.search import SearchQuery

logger = get_logger()


class NoSpatialMetadataError(Exception):
    """Raised when a granule has no usable spatial metadata in UMM."""


def _parse_umm_polygon(
    umm_data: dict[str, Any],
) -> result.Result[Polygon, NoSpatialMetadataError]:
    """Extract a Shapely Polygon representing the granule footprint from CMR UMM metadata.

    Handles multiple ``BoundingRectangles`` (e.g. descending passes split at the
    antimeridian) by unioning them into a single geometry.  Also handles
    ``GPolygons`` (the standard CMR key for granule-level polygon footprints,
    used by VIIRS, MODIS, and most polar-orbiting products) and falls back to
    the ``Polygons`` key.

    Returns:
        ``Success(polygon)`` on success, ``Failure(reason)`` when the granule
        carries no usable spatial metadata.
    """
    spatial = umm_data.get("SpatialExtent", {})
    horizontal = spatial.get("HorizontalSpatialDomain", {})
    geometry = horizontal.get("Geometry", {})

    # Try BoundingRectangles — union all of them
    bboxes = geometry.get("BoundingRectangles", [])
    if bboxes:
        polys = []
        for bbox in bboxes:
            w = bbox.get("WestBoundingCoordinate", 0)
            s = bbox.get("SouthBoundingCoordinate", 0)
            e = bbox.get("EastBoundingCoordinate", 0)
            n = bbox.get("NorthBoundingCoordinate", 0)
            polys.append(Polygon([(w, s), (e, s), (e, n), (w, n)]))
        return result.Success(unary_union(polys))

    # Try GPolygons — the standard CMR key for granule-level footprints
    gpolygons = geometry.get("GPolygons", [])
    if gpolygons:
        boundary = gpolygons[0].get("Boundary", {})
        points = boundary.get("Points", [])
        if points:
            coords = [(p.get("Longitude", 0), p.get("Latitude", 0)) for p in points]
            return result.Success(Polygon(coords))

    # Try Polygons (less common, kept as fallback)
    polygons = geometry.get("Polygons", [])
    if polygons:
        boundary = polygons[0].get("Boundary", {})
        points = boundary.get("Points", [])
        if points:
            coords = [(p.get("Longitude", 0), p.get("Latitude", 0)) for p in points]
            return result.Success(Polygon(coords))

    return result.Failure(
        NoSpatialMetadataError("Granule has no usable spatial metadata in UMM")
    )


@plugin(name="earthaccess", category="search")
def search_earthaccess(query: SearchQuery) -> gpd.GeoDataFrame:
    """Search for earthaccess data given a SearchQuery.

    Args:
        query: A ``SearchQuery`` containing products, time_range, and optionally
            spatial_extent, cell_overlap_mode, and extra options passed
            directly to ``earthaccess.search_data``.

    Returns:
        A ``gpd.GeoDataFrame`` with columns: product_name, granule_id, concept_id,
        start_time, end_time, s3_url, https_url, size_mb, geometry, and (when
        *spatial_extent* is given) grid_cells.

    Raises:
        ValueError: If both *spatial_extent* and *bounding_box* are specified.
    """
    if query.spatial_extent and "bounding_box" in query.options:
        raise ValueError(
            "Cannot specify both 'spatial_extent' and 'bounding_box'. "
            "The spatial_extent automatically derives the bounding box."
        )

    temporal = (
        query.time_range.start.strftime("%Y-%m-%d %H:%M:%S"),
        query.time_range.end.strftime("%Y-%m-%d %H:%M:%S"),
    )

    short_names = [p.name for p in query.products]

    # Apply bounding box filter if spatial_extent is provided
    kwargs_for_search = dict(query.options)
    if query.spatial_extent and query.spatial_extent.grid_cells:
        all_bounds = unary_union(
            [cell.bounds for cell in query.spatial_extent.grid_cells]
        )
        minx, miny, maxx, maxy = all_bounds.bounds
        kwargs_for_search["bounding_box"] = (minx, miny, maxx, maxy)

    results = earthaccess.search_data(
        short_name=short_names, temporal=temporal, **kwargs_for_search
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
    if query.spatial_extent:
        columns.append("grid_cells")

    if not results:
        return gpd.GeoDataFrame(columns=[*columns, "geometry"], geometry="geometry")

    rows = []
    geometries = []
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

        # Parse the granule footprint geometry
        poly_result = _parse_umm_polygon(umm)
        granule_poly = None
        match poly_result:
            case result.Success(poly):
                granule_poly = poly
            case result.Failure(e):
                logger.warning(
                    "Failed to parse UMM polygon",
                    error=e,
                    granule_id=meta.get("native-id"),
                )

        row_data: dict[str, Any] = {
            "product_name": extracted_product_name,
            "granule_id": meta.get("native-id"),
            "concept_id": meta.get("concept-id"),
            "start_time": pd.to_datetime(start_time) if start_time else None,
            "end_time": pd.to_datetime(end_time) if end_time else None,
            "s3_url": s3_url,
            "https_url": https_url,
            "size_mb": granule.size(),
        }

        # Check cell overlap if a spatial extent was requested
        if query.spatial_extent:
            contained_cells: list[str] = []
            if granule_poly is not None:
                overlap_fn = (
                    granule_poly.contains
                    if query.cell_overlap_mode == "contains"
                    else granule_poly.intersects
                )
                contained_cells = [
                    f"{cell.row}_{cell.col}"
                    for cell in query.spatial_extent.grid_cells
                    if overlap_fn(cell.bounds)
                ]
            row_data["grid_cells"] = contained_cells

        rows.append(row_data)
        geometries.append(granule_poly)

    return gpd.GeoDataFrame(rows, geometry=geometries)
