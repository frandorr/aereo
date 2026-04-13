"""Core spatial models for grid cells and grid definitions.

Defines GridCell, GridDefinition, and OverlapMode for representing
spatial grid systems, coordinate transformations, and pyresample
AreaDefinition generation.
"""

import json
from copy import deepcopy
from enum import Enum
from functools import lru_cache
from typing import Any, Literal, Mapping, Protocol

import attrs
import geopandas as gpd
from aer.schemas import SearchResultSchema
from majortom_eg.MajorTom import MajorTomGrid
from pandera.typing.geopandas import GeoDataFrame  # type: ignore[no-redef]
from pyresample.geometry import AreaDefinition
from shapely.geometry import Polygon, shape
from structlog import get_logger

from .utils import get_utm_epsg_from_geometry

logger = get_logger()


# Define a protocol for objects that have a __geo_interface__ property
# like pystac-client https://github.com/stac-utils/pystac-client/blob/main/pystac_client/item_search.py#L54
class GeoInterface(Protocol):
    @property
    def __geo_interface__(self) -> dict[str, Any]: ...


def _format_geom(
    value: str | dict[str, Any] | GeoInterface | None,
) -> dict[str, Any]:
    if value is None:
        raise Exception("GEom value cannot be None")
    if isinstance(value, dict):
        if value.get("type") == "Feature":
            geom = deepcopy(value.get("geometry"))
            if geom is None:
                raise Exception("Feature must have a geometry")
            return geom
        else:
            return deepcopy(value)
    if isinstance(value, str):
        return dict(json.loads(value))
    if hasattr(value, "__geo_interface__"):
        return dict(deepcopy(getattr(value, "__geo_interface__")))
    raise Exception(
        "value must be of type None, str, dict, or an object that "
        "implements __geo_interface__"
    )


@attrs.frozen
class GeomLike(Mapping):
    """A simple wrapper for geometric objects that behaves like a read-only geojson dict."""

    _geom: dict[str, Any] = attrs.field(converter=_format_geom)

    def __getitem__(self, key: str) -> Any:
        return self._geom[key]

    def __iter__(self):
        return iter(self._geom)

    def __len__(self) -> int:
        return len(self._geom)


class OverlapMode(Enum):
    """Enumeration for different modes of handling overlapping geometries."""

    INTERSECTS = "intersects"
    WITHIN = "within"
    CONTAINS = "contains"


def find_overlapping_cells(
    grid: MajorTomGrid, geom: Polygon, overlap_mode: OverlapMode
) -> list[dict[str, Any]]:
    overlapping = list(grid.generate_grid_cells(geom))
    if not overlapping:
        return []
    cells = []
    for cell in overlapping:
        cell_geom = cell.geom
        relation = overlap_mode.value
        if relation == "intersects" and not cell_geom.intersects(geom):
            continue
        if relation == "within" and not cell_geom.within(geom):
            continue
        if relation == "contains" and not cell_geom.contains(geom):
            continue
        utm_epsg = get_utm_epsg_from_geometry(cell_geom)
        cells.append(
            {
                "cell_id": cell.id(),
                "cell_footprint": cell_geom,
                "utm_crs": f"EPSG:{utm_epsg}",
            }
        )
    return cells


def add_overlapping_cells(
    gdf: GeoDataFrame[SearchResultSchema],
    aoi: GeomLike,
    grid: MajorTomGrid,
    overlap_mode: OverlapMode = OverlapMode.INTERSECTS,
) -> GeoDataFrame[SearchResultSchema]:
    """Add overlapping grid cells to a GeoDataFrame based on an AOI and a grid definition.

    Args:
        gdf (GeoDataFrame): Input GeoDataFrame with search results.
        aoi (GeomLike): Area of interest as a geometric object.
        grid (MajorTomGrid): Grid definition to use for finding overlapping cells.
        overlap_mode (OverlapMode): Mode to determine how to find overlapping cells (default is INTERSECTS).

    Returns:
        GeoDataFrame: Updated GeoDataFrame with overlapping grid cells added.
    """

    results: list[dict[str, Any]] = []
    for idx, row in gdf.iterrows():
        row_geom = row.geometry
        # Convert AOI to shapely geometry for intersection

        aoi_geom = shape(dict(aoi))
        # Calculate intersection between row geometry and AOI
        intersecting_aoi = row_geom.intersection(aoi_geom)
        # Use intersection for finding overlapping cells
        overlapping_cells = find_overlapping_cells(grid, intersecting_aoi, overlap_mode)
        original_geom = gdf.geometry.iloc[idx]
        if not overlapping_cells:
            result_row = dict(row)
            result_row["geometry"] = original_geom
            result_row["cell_id"] = None
            result_row["cell_footprint"] = None
            result_row["utm_crs"] = None
            result_row["intersecting_aoi"] = (
                intersecting_aoi
                if intersecting_aoi and not intersecting_aoi.is_empty
                else None
            )
            results.append(result_row)
        for cell in overlapping_cells:
            result_row = dict(row)
            result_row["geometry"] = original_geom
            result_row["cell_id"] = cell["cell_id"]
            result_row["cell_footprint"] = cell["cell_footprint"]
            result_row["utm_crs"] = cell["utm_crs"]
            result_row["intersecting_aoi"] = (
                intersecting_aoi
                if intersecting_aoi and not intersecting_aoi.is_empty
                else None
            )
            results.append(result_row)

    return gpd.GeoDataFrame(results)  # type: ignore[return-value]


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
