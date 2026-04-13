"""MajorTom-compliant grid generation and validation.

Implements the Grid class for creating global spatial grids with
configurable cell sizes, latitude/longitude ranges, and UTM zone
definitions. Includes GridSchema for validating grid GeoDataFrames.
"""

import math
from pathlib import Path
from typing import cast

import geopandas as gpd
import numpy as np
import pandas as pd
from aer.schemas import GridSchema
from shapely.geometry import Polygon
from structlog import get_logger

from .utils import get_utm_zone_from_latlng, reproject_geom

logger = get_logger(__name__)


class Grid:
    RADIUS_EQUATOR = 6378.137  # km

    def __init__(
        self,
        name: str,
        dist: int,
        latitude_range=(-80, 84),
        longitude_range=(-180, 180),
        utm_definition="center",
    ):
        self.name = name
        self.dist = dist
        self.dist_km = dist / 1000  # Convert meters to km for calculations
        self.latitude_range = latitude_range
        self.longitude_range = longitude_range
        self.utm_definition = utm_definition
        self.rows, self.lats = self.get_rows()
        self.points, self.points_by_row = self.get_points()
        # Store original point geometries before computing footprints
        self.points["point_geometry"] = self.points.geometry.copy()
        # apply footprint method to each point
        self.points["geometry"] = self.points.apply(self.get_bounded_footprint, axis=1)
        self.points.set_geometry("geometry", inplace=True)
        self.points["utm_footprint"] = self.points.apply(
            lambda row: reproject_geom(row.geometry, "EPSG:4326", row["utm_crs"]),
            axis=1,
        )
        # validate self.points with grid schema
        GridSchema.validate(self.points)

    def get_rows(self):
        # Define set of latitudes to use, based on the grid distance
        arc_pole_to_pole = math.pi * self.RADIUS_EQUATOR
        num_divisions_in_hemisphere = math.ceil(arc_pole_to_pole / self.dist_km)

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
        num_divisions = math.ceil(circumference / self.dist_km)
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
        points_by_row: list[gpd.GeoDataFrame] = [None] * len(self.rows)  # type: ignore[assignment]
        for r, lat in zip(self.rows, self.lats):
            (
                point_names,
                grid_row_names,
                grid_col_names,
                grid_lats,
                grid_lons,
                utm_zones,
                epsgs,
            ) = [], [], [], [], [], [], []
            cols, lons = self.subdivide_circumference(lat, return_cols=True)  # pyright: ignore[reportUnknownVariableType,reportCallIssue]

            cols, lons = self.filter_longitude(cols, lons)  # pyright: ignore[reportUnknownArgumentType]
            for c, lon in zip(cols, lons):
                point_names.append(f"{r}_{c}")
                grid_row_names.append(r)
                grid_col_names.append(c)
                grid_lats.append(lat)
                grid_lons.append(lon)
                if self.utm_definition == "bottomleft":
                    utm_zones.append(get_utm_zone_from_latlng([lat, lon]))
                elif self.utm_definition == "center":
                    center_lat = lat + (self.dist / 2) / 111_120
                    center_lat = max(min(center_lat, 84), -80)
                    center_lon = lon + (self.dist / 2) / (
                        111_120 * math.cos(center_lat * math.pi / 180)
                    )
                    center_lon = ((center_lon + 180) % 360) - 180
                    utm_zones.append(get_utm_zone_from_latlng([center_lat, center_lon]))
                else:
                    raise ValueError(f"Invalid utm_definition {self.utm_definition}")
                epsgs.append(f"EPSG:{utm_zones[-1]}")

            points_by_row[r_idx] = gpd.GeoDataFrame(
                {
                    "grid_cell": point_names,
                    "row": grid_row_names,
                    "col": grid_col_names,
                    "utm_crs": utm_zones,
                    "dist": [int(self.dist)] * len(point_names),
                },
                geometry=gpd.points_from_xy(grid_lons, grid_lats),  # pyright: ignore[reportUnknownArgumentType]
            )
            r_idx += 1
        points = gpd.GeoDataFrame(pd.concat(points_by_row))  # type: ignore

        return points, points_by_row

    def group_points_by_row(self):
        points_by_row: list[gpd.GeoDataFrame] = [None] * len(self.rows)  # type: ignore[assignment]
        for i, row in enumerate(self.rows):
            points_by_row[i] = cast(
                gpd.GeoDataFrame, self.points[self.points.row == row]
            )
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
                (self.points.row == row) & (self.points.col == col), "point_geometry"
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
        row_val = point["row"]
        col_val = point["col"]
        # Derive row_idx and col_idx from the actual index in self.rows (numpy array)
        row_idx = int(np.where(self.rows == row_val)[0][0])  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        # Get unique columns from the points DataFrame for this row
        row_df = self.points_by_row[row_idx]
        cols_for_row = row_df["col"].tolist()
        col_idx = cols_for_row.index(col_val)  # pyright: ignore[reportUnknownMemberType]
        next_row_idx = row_idx + 1  # pyright: ignore[reportUnknownVariableType]
        next_col_idx = col_idx + 1  # pyright: ignore[reportUnknownVariableType]

        if next_row_idx >= len(
            self.lats
        ):  # If at top row, use difference between top and second-to-top row for height
            height = self.lats[row_idx] - self.lats[row_idx - 1]  # pyright: ignore[reportUnknownVariableType]
            top = self.lats[row_idx] + height  # pyright: ignore[reportUnknownVariableType]
        else:
            top = self.lats[next_row_idx]

        row_df = self.points_by_row[row_idx]
        max_col: int = len(row_df) - 1  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType,reportUnknownArgumentType]
        if (
            next_col_idx > max_col
        ):  # If at rightmost column, use difference between rightmost and second-to-rightmost column for width
            width = (
                row_df.iloc[col_idx].geometry.x  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
                - row_df.iloc[col_idx - 1].geometry.x  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            )
            right = row_df.iloc[col_idx].geometry.x + width  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        else:
            right = row_df.iloc[next_col_idx].geometry.x  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]

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

    def save_to_parquet(self, output_path: Path | str):
        """Save grid points to a parquet file in the configured grid store."""
        output_path = (
            output_path if isinstance(output_path, Path) else Path(output_path)
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        gdf = self.points.reset_index(drop=True)
        # set geometry column to utm_footprint centroid for better compatibility with parquet (since some formats don't support complex geometries)
        gdf.set_geometry(gdf["utm_footprint"].centroid, inplace=True)  # pyright: ignore[reportUnknownMemberType]
        self.points.reset_index(drop=True).to_parquet(output_path)  # pyright: ignore[reportUnknownMemberType]
        logger.info(
            "Grid saved to parquet",
            grid_name=self.name,
            dist=self.dist,
            path=output_path,
        )
