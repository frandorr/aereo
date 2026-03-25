import attrs
import geopandas as gpd
from functools import cached_property
from shapely.geometry import Polygon
from pyresample.geometry import AreaDefinition
from aer.settings import ENV_SETTINGS
from pyproj import Transformer
from shapely.ops import transform
from returns import result
from pathlib import Path
import math
import numpy as np
import pandas as pd
import utm
from shapely.geometry import Point, MultiPolygon, LineString
from shapely.geometry.base import BaseGeometry

from typing import Any
import pandera.pandas as pa
from pandera.typing import Series
from pandera.typing.geopandas import GeoSeries


class GridSchema(pa.DataFrameModel):  # type: ignore[misc]
    """Schema for validating a MajorTom-compliant grid GeoDataFrame.

    Defines the standard set of columns for the global 100km grid.
    """

    name: Series[pa.String] = pa.Field(nullable=False)
    row: Series[pa.String] = pa.Field(nullable=False)
    col: Series[pa.String] = pa.Field(nullable=False)
    row_idx: Series[pa.Int64] = pa.Field(nullable=False)
    col_idx: Series[pa.Int64] = pa.Field(nullable=False)
    utm_zone: Series[pa.String] = pa.Field(nullable=False)
    epsg: Series[pa.String] = pa.Field(nullable=False)
    geometry: GeoSeries[Any] = pa.Field(nullable=False)
    cell_bounds: GeoSeries[Any] = pa.Field(nullable=False)

    class Config:
        strict = False
        coerce = True


class GridNotFoundError(Exception):
    """Exception raised when a grid is not found."""

    pass


def reproject_polygon(polygon: Polygon, src_epsg: str, dst_epsg: str) -> Polygon:
    """
    Reproject a polygon to a different coordinate system.
    Args:
        polygon (Polygon): Shapely Polygon in source coordinate system
        src_epsg (str): Source EPSG code
        dst_epsg (str): Destination EPSG code
    Returns:
        Polygon: Reprojected Shapely Polygon in destination coordinate system
    """
    transformer = Transformer.from_crs(src_epsg, dst_epsg, always_xy=True)
    projected_polygon = transform(transformer.transform, polygon)
    return projected_polygon


@attrs.frozen
class GridCell:
    """A spatial grid cell representation.

    Attributes:
        row (str): The row identifier of the grid cell.
        col (str): The column identifier of the grid cell.
        dist (int): The distance or resolution metric for the grid cell.
        bounds (Polygon): The spatial boundary of the cell as a Shapely Polygon.
        epsg (str): The EPSG spatial reference system code.
    """

    row: str
    col: str
    dist: int
    bounds: Polygon
    epsg: str

    # NOTE: cached_property works with attrs.frozen because attrs does not use
    # __slots__ by default. If slots=True is ever enabled, replace with
    # functools.lru_cache or attrs.field(init=False).
    @cached_property
    def utm_bounds(self) -> Polygon:
        """Get the bounds of the grid cell in UTM coordinates.

        Returns:
            Polygon: The bounds of the grid cell in UTM coordinates.
        """
        return reproject_polygon(self.bounds, "epsg:4326", self.epsg)

    def area_name(self, resolution: int) -> str:
        """
        Get the area name based on grid cell and a resolution in meters.
        Args:
            resolution (int): Resolution in meters
        Returns:
            str: Area name

        """
        return f"{self.row}_{self.col}_{self.dist}km_{resolution}m"

    def area_def(self, resolution: int) -> AreaDefinition:
        """Get a pyresample AreaDefinition from a GridCell.

        Args:
            resolution (int): Resolution in meters
        Returns:
            AreaDefinition: Pyresample AreaDefinition
        """
        bounds = self.utm_bounds.bounds  # minx, miny, maxx, maxy
        area_extent = (bounds[0], bounds[1], bounds[2], bounds[3])
        width, height = (self.dist * 1000 // resolution, self.dist * 1000 // resolution)
        area_name = self.area_name(resolution)
        area_def = AreaDefinition(
            area_id=area_name,
            description=f"Area defined for {area_name} in {self.epsg}",
            proj_id=self.epsg,
            projection=self.epsg,
            area_extent=area_extent,
            width=width,
            height=height,
        )
        return area_def


@attrs.frozen
class GridSpatialExtent:
    """A collection of grid cells representing a spatial area.

    Attributes:
        grid_cells (frozenset[GridCell]): An immutable set of GridCell objects.
    """

    grid_cells: frozenset[GridCell]

    def intersects(self, other: "GridSpatialExtent") -> bool:
        """Check if this grid spatial extent intersects with another.

        Args:
            other (GridSpatialExtent): The other grid spatial extent to check.

        Returns:
            bool: True if there is at least one overlapping grid cell, False otherwise.
        """
        return not self.grid_cells.isdisjoint(other.grid_cells)

    def intersection(self, other: "GridSpatialExtent") -> "GridSpatialExtent":
        """Get the intersection of this grid spatial extent with another.

        Args:
            other (GridSpatialExtent): The other grid spatial extent.

        Returns:
            GridSpatialExtent: A new GridSpatialExtent containing the common grid cells.
        """
        return GridSpatialExtent(self.grid_cells & other.grid_cells)


@attrs.frozen
class GridDefinition:
    """Definition of a spatial grid system.

    Attributes:
        name (str): The name of the grid definition.
        dist (int): The grid cell size or distance metric (e.g., in kilometers).
    """

    name: str
    dist: int

    def load_grid(self) -> result.Result[gpd.GeoDataFrame, GridNotFoundError]:
        """Load grid points from a parquet file."""
        # check if it is default grid
        current_file_dir = Path(__file__).parent
        grid_path = current_file_dir / f"grid_{self.name}_{self.dist}km.parquet"
        if grid_path.exists():
            gdf = gpd.read_parquet(grid_path)
            return result.Success(gdf)

        # try to load from grid store
        grid_path = (
            ENV_SETTINGS.GRID_STORE_PATH / f"grid_{self.name}_{self.dist}km.parquet"
        )
        try:
            gdf = gpd.read_parquet(grid_path)  # pyright: ignore[reportUnknownMemberType]
            return result.Success(gdf)
        except Exception:
            return result.Failure(
                GridNotFoundError(f"Grid file at {grid_path} not found.")
            )

    @cached_property
    def grid(self) -> gpd.GeoDataFrame:
        """Load grid points from a parquet file.

        Returns:
            gpd.GeoDataFrame: Grid points.
        Raises:
            ValueError: If the grid file is empty.
        """
        # check path exists
        gdf_result = self.load_grid()
        match gdf_result:
            case result.Success(gdf):
                if gdf.empty:
                    raise ValueError("Grid is empty.")
                return gdf
            case result.Failure(_):
                raise GridNotFoundError("Grid not found. Create grid first.")

    def intersecting_grid_spatial_extent(self, geometry: Polygon) -> GridSpatialExtent:
        """Get all grid cells that intersect with a given geometry.

        Args:
            geometry (Polygon): The geometry to check for intersections.

        Returns:
            GridSpatialExtent: A grid spatial extent containing all grid cells that intersect with the geometry.
        """
        intersecting_rows = self.grid[self.grid.intersects(geometry)]
        cells = []
        for _, row_data in intersecting_rows.iterrows():
            cells.append(  # pyright: ignore[reportUnknownMemberType]
                GridCell(
                    row=row_data["row"],
                    col=row_data["col"],
                    dist=self.dist,
                    bounds=row_data["cell_bounds"],
                    epsg=row_data["epsg"],
                )
            )
        return GridSpatialExtent(frozenset(cells))  # pyright: ignore[reportUnknownVariableType]


def get_utm_epsg_from_geometry(geometry: BaseGeometry) -> str:
    """
    Get the UTM EPSG code from a Shapely geometry.
    Args:
        geometry (BaseGeometry): A Shapely geometry object.
    Returns:
        str: The UTM EPSG code as a string.
    Raises:
        ValueError: If the geometry type is not supported.
    """

    if isinstance(geometry, (Polygon, MultiPolygon, LineString)):
        lonlat = (geometry.centroid.x, geometry.centroid.y)
    elif isinstance(geometry, Point):
        lonlat = (geometry.x, geometry.y)
    else:
        # raise an error if the geometry is not supported
        raise ValueError("Unsupported geometry type")

    _, _, zone_number, zone_letter = utm.from_latlon(lonlat[1], lonlat[0])  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]

    if zone_number and zone_letter:
        epsg = f"{326 if zone_letter >= 'N' else 327}{zone_number:02d}"
    else:
        raise ValueError("Could not determine UTM zone from geometry")

    return epsg


def get_utm_zone_from_latlng(latlng: list[float] | tuple[float, float]) -> str:
    """
    Get the UTM zone from a latlng list and return the corresponding EPSG code.

    Parameters
    ----------
    latlng : List[Union[int, float]]
        The latlng list to get the UTM zone from.

    Returns
    -------
    str
        The EPSG code for the UTM zone.
    """
    assert isinstance(latlng, (list, tuple)), (
        "latlng must be in the form of a list or tuple."
    )

    longitude = float(latlng[1])
    latitude = float(latlng[0])

    return get_utm_epsg_from_geometry(Point(longitude, latitude))


class Grid:
    RADIUS_EQUATOR = 6378.137  # km

    def __init__(
        self,
        name: str,
        dist: int | float,
        latitude_range=(-80, 84),
        longitude_range=(-180, 180),
        utm_definition="bottomleft",
    ):
        self.name = name
        self.dist = dist
        self.latitude_range = latitude_range
        self.longitude_range = longitude_range
        self.utm_definition = utm_definition
        self.rows, self.lats = self.get_rows()
        self.points, self.points_by_row = self.get_points()
        # apply footprint method to each point
        self.points["cell_bounds"] = self.points.apply(
            self.get_bounded_footprint, axis=1
        )

    def get_rows(self):
        # Define set of latitudes to use, based on the grid distance
        arc_pole_to_pole = math.pi * self.RADIUS_EQUATOR
        num_divisions_in_hemisphere = math.ceil(arc_pole_to_pole / self.dist)

        latitudes = np.linspace(-90, 90, num_divisions_in_hemisphere + 1)[:-1]
        latitudes = np.mod(latitudes, 180) - 90

        # order should be from south to north
        latitudes = np.sort(latitudes)

        zeroth_row = np.searchsorted(latitudes, 0)

        # From 0U-NU and 1D-ND
        rows: list[str | None] = [None] * len(latitudes)
        rows[zeroth_row:] = [f"{i}U" for i in range(len(latitudes) - zeroth_row)]
        rows[:zeroth_row] = [f"{abs(i - zeroth_row)}D" for i in range(zeroth_row)]  # pyright: ignore[reportUnknownArgumentType]

        # bound to range
        idxs = (latitudes >= self.latitude_range[0]) * (
            latitudes <= self.latitude_range[1]
        )
        rows_arr, latitudes_arr = np.array(rows), np.array(latitudes)
        rows_arr, latitudes_arr = rows_arr[idxs], latitudes_arr[idxs]

        return rows_arr, latitudes_arr  # pyright: ignore[reportUnknownVariableType]

    def get_circumference_at_latitude(self, lat: float) -> float:
        # Circumference of the cross-section of a sphere at a given latitude

        radius_at_lat = self.RADIUS_EQUATOR * math.cos(lat * math.pi / 180)
        circumference = 2 * math.pi * radius_at_lat

        return circumference

    def subdivide_circumference(self, lat: float, return_cols=False):
        # Provide a list of longitudes that subdivide the circumference of the earth at a given latitude
        # into equal parts as close as possible to dist

        circumference = self.get_circumference_at_latitude(lat)
        num_divisions = math.ceil(circumference / self.dist)
        longitudes = np.linspace(-180, 180, num_divisions + 1)[:-1]
        longitudes = np.mod(longitudes, 360) - 180
        longitudes = np.sort(longitudes)

        if return_cols:
            cols: list[str | None] = [None] * len(longitudes)
            zeroth_idx = np.where(longitudes == 0)[0][0]
            cols[zeroth_idx:] = [f"{i}R" for i in range(len(longitudes) - zeroth_idx)]
            cols[:zeroth_idx] = [f"{abs(i - zeroth_idx)}L" for i in range(zeroth_idx)]  # pyright: ignore[reportUnknownArgumentType]
            return np.array(cols), np.array(longitudes)

        return np.array(longitudes)

    def get_points(self):
        r_idx = 0
        points_by_row = [None] * len(self.rows)
        for r, lat in zip(self.rows, self.lats):
            (
                point_names,
                grid_row_names,
                grid_col_names,
                grid_row_idx,
                grid_col_idx,
                grid_lats,
                grid_lons,
                utm_zones,
                epsgs,
            ) = [], [], [], [], [], [], [], [], []
            cols, lons = self.subdivide_circumference(lat, return_cols=True)  # pyright: ignore[reportUnknownVariableType,reportCallIssue]

            cols, lons = self.filter_longitude(cols, lons)  # pyright: ignore[reportUnknownArgumentType]
            c_idx = 0
            for c, lon in zip(cols, lons):
                point_names.append(f"{r}_{c}")
                grid_row_names.append(r)
                grid_col_names.append(c)
                grid_row_idx.append(r_idx)
                grid_col_idx.append(c_idx)
                grid_lats.append(lat)
                grid_lons.append(lon)
                if self.utm_definition == "bottomleft":
                    utm_zones.append(get_utm_zone_from_latlng([lat, lon]))
                elif self.utm_definition == "center":
                    center_lat = lat + (1000 * self.dist / 2) / 111_120
                    center_lon = lon + (1000 * self.dist / 2) / (
                        111_120 * math.cos(center_lat * math.pi / 180)
                    )
                    utm_zones.append(get_utm_zone_from_latlng([center_lat, center_lon]))
                else:
                    raise ValueError(f"Invalid utm_definition {self.utm_definition}")
                epsgs.append(f"EPSG:{utm_zones[-1]}")

                c_idx += 1
            points_by_row[r_idx] = gpd.GeoDataFrame(
                {
                    "name": point_names,
                    "row": grid_row_names,
                    "col": grid_col_names,
                    "row_idx": grid_row_idx,
                    "col_idx": grid_col_idx,
                    "utm_zone": utm_zones,
                    "epsg": epsgs,
                },
                geometry=gpd.points_from_xy(grid_lons, grid_lats),  # pyright: ignore[reportUnknownArgumentType]
            )
            r_idx += 1
        points = gpd.GeoDataFrame(pd.concat(points_by_row))  # pyright: ignore[reportUnknownMemberType]

        return points, points_by_row

    def group_points_by_row(self):
        # Make list of different gdfs for each row
        points_by_row = [None] * len(self.rows)
        for i, row in enumerate(self.rows):
            points_by_row[i] = self.points[self.points.row == row]
        return points_by_row

    def filter_longitude(self, cols, lons):
        idxs = (lons >= self.longitude_range[0]) * (lons <= self.longitude_range[1])
        cols, lons = cols[idxs], lons[idxs]
        return cols, lons

    def latlon2rowcol(self, lats, lons, return_idx=False, integer=False):
        """
        Convert latitude and longitude to row and column number from the grid
        """
        # Always take bottom left corner of grid cell
        rows = np.searchsorted(self.lats, lats) - 1

        # Get the possible points of the grid cells at the given latitude
        possible_points = [self.points_by_row[row] for row in rows]  # pyright: ignore[reportUnknownArgumentType]
        # For each point, find the rightmost point that is still to the left of the given longitude
        cols = [
            poss_points.iloc[np.searchsorted(poss_points.geometry.x, lon) - 1].col  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            for poss_points, lon in zip(possible_points, lons)
        ]
        out_rows = self.rows[rows].tolist()

        outputs = [out_rows, cols]
        if return_idx:
            # Get the table index for self.points with each row,col pair in rows, cols
            idx = [
                self.points[
                    (self.points.row == row) & (self.points.col == col)
                ].index.values[0]  # pyright: ignore[reportUnknownMemberType]
                for row, col in zip(out_rows, cols)
            ]
            outputs.append(idx)

        # return raw numbers
        if integer:
            outputs[0] = [
                int(el[:-1]) if el[-1] == "U" else -int(el[:-1]) for el in outputs[0]
            ]  # pyright: ignore[reportUnknownVariableType]
            outputs[1] = [
                int(el[:-1]) if el[-1] == "R" else -int(el[:-1]) for el in outputs[1]
            ]  # pyright: ignore[reportUnknownVariableType]

        return outputs

    def rowcol2latlon(self, rows, cols):
        point_geoms = [
            self.points.loc[
                (self.points.row == row) & (self.points.col == col), "geometry"
            ].values[0]  # pyright: ignore[reportUnknownMemberType]
            for row, col in zip(rows, cols)
        ]
        lats = [point.y for point in point_geoms]  # pyright: ignore[reportUnknownVariableType]
        lons = [point.x for point in point_geoms]  # pyright: ignore[reportUnknownVariableType]
        return lats, lons

    def get_bounded_footprint(self, point, buffer_ratio=0):
        # Gets the polygon footprint of the grid cell for a given point, bounded by the other grid points' cells.
        # Grid point defined as bottom-left corner of polygon. Buffer ratio is the ratio of the grid cell's width/height to buffer by.

        bottom, left = point.geometry.y, point.geometry.x  # pyright: ignore[reportUnknownMemberType]
        row_idx = point.row_idx  # pyright: ignore[reportUnknownMemberType]
        col_idx = point.col_idx  # pyright: ignore[reportUnknownMemberType]
        next_row_idx = row_idx + 1  # pyright: ignore[reportUnknownVariableType]
        next_col_idx = col_idx + 1  # pyright: ignore[reportUnknownVariableType]

        if next_row_idx >= len(
            self.lats
        ):  # If at top row, use difference between top and second-to-top row for height
            height = self.lats[row_idx] - self.lats[row_idx - 1]  # pyright: ignore[reportUnknownVariableType]
            top = self.lats[row_idx] + height  # pyright: ignore[reportUnknownVariableType]
        else:
            top = self.lats[next_row_idx]

        max_col: int = len(self.points_by_row[row_idx].col_idx) - 1  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType,reportUnknownArgumentType]
        if (
            next_col_idx > max_col
        ):  # If at rightmost column, use difference between rightmost and second-to-rightmost column for width
            width = (
                self.points_by_row[row_idx].iloc[col_idx].geometry.x  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
                - self.points_by_row[row_idx].iloc[col_idx - 1].geometry.x  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            )
            right = self.points_by_row[row_idx].iloc[col_idx].geometry.x + width  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        else:
            right = self.points_by_row[row_idx].iloc[next_col_idx].geometry.x  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]

        # Buffer the polygon by the ratio of the grid cell's width/height
        width = right - left  # pyright: ignore[reportUnknownVariableType]
        height = top - bottom  # pyright: ignore[reportUnknownVariableType]

        buffer_horizontal = width * buffer_ratio
        buffer_vertical = height * buffer_ratio

        new_left = left - buffer_horizontal  # pyright: ignore[reportUnknownVariableType]
        new_right = right + buffer_horizontal

        new_bottom = bottom - buffer_vertical  # pyright: ignore[reportUnknownVariableType]
        new_top = top + buffer_vertical

        bbox = Polygon(
            [
                (new_left, new_bottom),
                (new_left, new_top),
                (new_right, new_top),
                (new_right, new_bottom),
            ]
        )  # pyright: ignore[reportUnknownArgumentType]

        return bbox

    def save_to_parquet(self):
        """Save grid points to a parquet file in the configured grid store."""
        ENV_SETTINGS.GRID_STORE_PATH.mkdir(parents=True, exist_ok=True)
        self.points.reset_index(drop=True).to_parquet(
            ENV_SETTINGS.GRID_STORE_PATH / f"grid_{self.name}_{self.dist}km.parquet"
        )  # pyright: ignore[reportUnknownMemberType]
