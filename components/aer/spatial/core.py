from enum import Enum
from functools import lru_cache
from typing import Literal

import attrs
from pyresample.geometry import AreaDefinition
from shapely.geometry import Polygon
from structlog import get_logger

logger = get_logger()


class OverlapMode(Enum):
    """Enumeration for different modes of handling overlapping geometries."""

    INTERSECTS = "intersects"
    WITHIN = "within"
    CONTAINS = "contains"


@attrs.frozen
class GridCell:
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
