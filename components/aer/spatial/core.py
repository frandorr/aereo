"""Core spatial models for grid cells and grid definitions.

Defines GridCell, GridDefinition, and OverlapMode for representing
spatial grid systems, coordinate transformations, and pyresample
AreaDefinition generation.
"""

from enum import Enum
from functools import lru_cache
from typing import Literal

import attrs
import geopandas as gpd
from aer.schemas import AssetSchema
from majortom_eg.MajorTom import GridCell, MajorTomGrid
from pandera.typing.geopandas import GeoDataFrame  # type: ignore[no-redef]
from pyresample.geometry import AreaDefinition
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from structlog import get_logger

from .utils import get_utm_epsg_from_geometry

logger = get_logger()


class OverlapMode(Enum):
    """Enumeration for different modes of handling overlapping geometries."""

    INTERSECTS = "intersects"
    WITHIN = "within"
    CONTAINS = "contains"


@lru_cache(maxsize=16)
def find_overlapping_cells(
    grid: MajorTomGrid,
    geom: Polygon | MultiPolygon,
    intersecting_geom: Polygon | None = None,
    overlap_mode: OverlapMode = OverlapMode.INTERSECTS,
) -> tuple[list[GridCell], BaseGeometry]:
    if intersecting_geom is not None:
        # intersects geom with intersecting_geom to get the actual geometry to check against the grid
        geom = geom.intersection(intersecting_geom)  # type: ignore[assignment]
        if geom.is_empty:
            return [], geom  # pyright: ignore[reportReturnType]
    overlapping = list(grid.generate_grid_cells(geom))
    return overlapping, geom  # pyright: ignore[reportReturnType]


def add_overlapping_cells(
    gdf: GeoDataFrame[AssetSchema],
    aoi: Polygon | MultiPolygon,
    grid: MajorTomGrid,
    overlap_mode: OverlapMode = OverlapMode.INTERSECTS,
) -> GeoDataFrame[AssetSchema]:
    """Add overlapping grid cells to a GeoDataFrame based on an AOI and a grid definition.

    Uses pre-computed grid cells and STRtree spatial index for O(log n) lookups.

    Args:
        gdf (GeoDataFrame): Input GeoDataFrame with search results.
        aoi (Polygon | MultiPolygon): Area of interest as a shapely geometry.
        grid (MajorTomGrid): Grid definition to use for finding overlapping cells.
        overlap_mode (OverlapMode): Mode to determine how to find overlapping cells (default is INTERSECTS).

    Returns:
        GeoDataFrame: Updated GeoDataFrame with overlapping grid cells added.
    """
    from tqdm import tqdm

    results = []
    for _, row in tqdm(gdf.iterrows()):
        row_geom = row.geometry
        matching_cells, intersecting_geom = find_overlapping_cells(
            grid=grid,
            geom=row_geom,
            intersecting_geom=aoi,
            overlap_mode=overlap_mode,
        )

        if not matching_cells:
            result_row = dict(row)
            result_row["geometry"] = row_geom
            result_row["cell_id"] = None
            result_row["cell_footprint"] = None
            result_row["utm_crs"] = None
            result_row["intersecting_aoi"] = intersecting_geom
            results.append(result_row)
            continue

        for cell in matching_cells:
            cell_geom = cell.geom  # pyright: ignore[reportAttributeAccessIssue]
            result_row = dict(row)
            result_row["geometry"] = row_geom
            result_row["cell_id"] = cell.id  # pyright: ignore[reportAttributeAccessIssue]
            result_row["cell_footprint"] = cell_geom
            result_row["utm_crs"] = f"EPSG:{get_utm_epsg_from_geometry(cell_geom)}"
            result_row["intersecting_aoi"] = intersecting_geom
            results.append(result_row)

    return gpd.GeoDataFrame(results)  # pyright: ignore[reportReturnType]


@attrs.frozen
class GridCellOri:
    """
    A single grid cell with spatial properties.

    Attributes:
    - grid_cell (str): Unique identifier for the grid cell (e.g., "0U_0R").
    - footprint (Polygon): The footprint of the grid cell in epsg:4326 (WGS84).
    - utm_footprint (Polygon): The footprint of the grid cell in UTM coordinates.
    - utm_crs (str): The EPSG code for the UTM coordinate reference system.
    - dist (int): The grid cell size in meters (e.g., 100000).
    """

    grid_cell: str
    footprint: Polygon
    utm_footprint: Polygon
    utm_crs: str
    dist: int

    def area_name(self, resolution: int) -> str:
        """
        Get the area name based on grid cell and a resolution in meters.
        Args:
            resolution (int): Resolution in meters
        Returns:
            str: Area name

        """
        return f"{self.grid_cell}_dist-{self.dist}m_res-{resolution}m"

    @lru_cache(maxsize=128)
    def area_def(self, resolution: int) -> AreaDefinition:
        """Get a pyresample AreaDefinition from a GridCell.

        Args:
            resolution (int): Resolution in meters
        Returns:
            AreaDefinition: Pyresample AreaDefinition
        """
        bounds = self.utm_footprint.bounds  # minx, miny, maxx, maxy
        area_extent = (bounds[0], bounds[1], bounds[2], bounds[3])
        width, height = (self.dist // resolution, self.dist // resolution)
        area_name = self.area_name(resolution)
        area_def = AreaDefinition(
            area_id=area_name,
            description=f"Area defined for {area_name} in {self.utm_crs}",
            proj_id=self.utm_crs,
            projection=self.utm_crs,
            area_extent=area_extent,
            width=width,
            height=height,
        )
        return area_def


@attrs.frozen
class GridDefinition:
    """Definition of a spatial grid system.

    Attributes:
        name (str): The name of the grid definition.
        dist (int): The grid cell size or distance metric (e.g., in meters).
        extent (tuple): The spatial extent of the grid defined as
                (min_lon, min_lat, max_lon, max_lat).
        utm_definition (str): The method for defining UTM zones, either "center" or "bottomleft".
    """

    name: str
    dist: int
    extent: tuple = (-180, -80, 180, 84)
    utm_definition: Literal["center", "bottomleft"] = "center"
