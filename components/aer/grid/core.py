from functools import cached_property
from typing import Sequence, cast

import numpy as np
import shapely
from aer.schemas import GridSchema
from aer.spatial import get_utm_epsg_from_geometry, reproject_geom
from majortom_eg.MajorTom import GridCell as BaseGridCell
from majortom_eg.MajorTom import MajorTomGrid
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry


class GridCell(BaseGridCell):
    """
    A grid cell that represents a polygon and whether it is a primary or overlapping cell.
    """

    def __init__(
        self,
        d: int,
        geom: shapely.geometry.Polygon,
        is_primary: bool = True,
        cell_id: str | None = None,
    ):
        """
        Initializes a GridCell with the given geometry and primary status.
        """
        super().__init__(geom=geom, is_primary=is_primary)
        self.D = d

        # Override the geohash ID from the base class if a Major TOM ID is provided
        if cell_id is not None:
            self._id = cell_id

    def to_geodataframe(self) -> GeoDataFrame[GridSchema]:
        """
        Converts the GridCell to a GeoDataFrame for easier spatial analysis and visualization.
        """
        import geopandas as gpd

        return cast(
            GeoDataFrame,
            gpd.GeoDataFrame(
                {
                    # Note: Changed id(self) to self.id() so it grabs the actual string ID
                    "grid_cell": [self.id()],
                    "grid_dist": [self.D],
                    "cell_geometry": [self.geom],
                    "cell_utm_crs": [self.utm_crs],
                    "cell_utm_footprint": [self.utm_footprint],
                }
            ),
        )

    @cached_property
    def utm_crs(self):
        return get_utm_epsg_from_geometry(self.geom)

    @cached_property
    def utm_footprint(self):
        return reproject_geom(self.geom, src_epsg="epsg:4326", dst_epsg=self.utm_crs)


class GridDefinition(MajorTomGrid):
    """
    A grid definition that generates grid cells intersecting a given polygon.
    It uses shapely for efficient geometry operations and supports both primary and overlapping grid cells.
    """

    def __init__(self, d: int = 10000, overlap=False):
        super().__init__(d=d, overlap=overlap)

    def cell_from_id(self, cell_id: str) -> GridCell:
        # Fallback: If no underscore, route to old geohash lookup logic
        if "_" not in cell_id:
            # Revert to base class method if it's an old geohash
            base_cell = super().cell_from_id(cell_id)
            return GridCell(
                self.D, base_cell.geom, base_cell.is_primary, cell_id=cell_id
            )

        # --- NEW O(1) LOOKUP ---
        parts = cell_id.split("_")
        y_str, x_str = parts[0], parts[1]
        is_primary = "OV" not in parts

        # Reverse-engineer relative Y (Row)
        y_val = int(y_str[:-1])
        rel_y = y_val if y_str[-1].upper() == "U" else -y_val

        # Reverse-engineer relative X (Col)
        x_val = int(x_str[:-1])
        rel_x = x_val if x_str[-1].upper() == "R" else -x_val

        # Map back to absolute indices
        row_idx = rel_y + int(self.row_count) // 2
        row_lat = self.get_row_lat(row_idx)

        lon_spacing = self.get_lon_spacing(row_lat)
        lon_offset = self.get_lon_offset(lon_spacing)

        n_cols = round(360 / lon_spacing) if lon_spacing > 0 else 0
        col_idx = rel_x + n_cols // 2

        cell_lon = self.get_col_lon(col_idx, lon_spacing, lon_offset)

        # Reconstruct exactly one Polygon instantly
        if is_primary:
            primary = Polygon(
                [
                    [cell_lon, row_lat],
                    [cell_lon + lon_spacing, row_lat],
                    [cell_lon + lon_spacing, row_lat + self.lat_spacing],
                    [cell_lon, row_lat + self.lat_spacing],
                ]
            )
            return GridCell(self.D, primary, is_primary=True, cell_id=cell_id)
        else:
            half_lat = self.lat_spacing / 2
            half_lon = lon_spacing / 2
            overlap_lon = cell_lon + half_lon
            overlap_lat = row_lat + half_lat
            overlap_poly = Polygon(
                [
                    [overlap_lon, overlap_lat],
                    [overlap_lon + lon_spacing, overlap_lat],
                    [overlap_lon + lon_spacing, overlap_lat + self.lat_spacing],
                    [overlap_lon, overlap_lat + self.lat_spacing],
                ]
            )
            return GridCell(self.D, overlap_poly, is_primary=False, cell_id=cell_id)

    def get_cell_name(self, row_idx, col_idx, lon_spacing, is_primary=True) -> str:
        """Generates the ESA Major TOM naming convention (e.g., 922D_249L)."""
        # 1. Calculate row relative to the Equator
        rel_y = row_idx - int(self.row_count) // 2
        y_dir = "U" if rel_y >= 0 else "D"

        # 2. Calculate col relative to the Prime Meridian
        n_cols = round(360 / lon_spacing) if lon_spacing > 0 else 0
        rel_x = col_idx - n_cols // 2
        x_dir = "R" if rel_x >= 0 else "L"

        name = f"{abs(rel_y)}{y_dir}_{abs(rel_x)}{x_dir}"

        # Append an indicator for overlapping grids
        if not is_primary:
            name += "_OV"

        return name

    def generate_grid_cells(self, polygon: BaseGeometry) -> Sequence[GridCell]:
        shapely.prepare(polygon)
        min_lon, min_lat, max_lon, max_lat = polygon.bounds
        if min_lon > max_lon:
            max_lon += 360

        start_row = int(np.floor((min_lat + 90 - self._lat_offset) / self.lat_spacing))
        end_row = int(np.ceil((max_lat + 90 - self._lat_offset) / self.lat_spacing))

        while self.get_row_lat(start_row) > min_lat + 1e-10:
            start_row -= 1
        while self.get_row_lat(end_row) < max_lat - 1e-10:
            end_row += 1

        cells = []

        # Process row by row
        for row_idx in range(start_row, end_row + 1):
            lat = self.get_row_lat(row_idx)
            lon_spacing = self.get_lon_spacing(lat)
            lon_offset = self.get_lon_offset(lon_spacing)

            start_col = int(np.floor((min_lon + 180 - lon_offset) / lon_spacing))
            end_col = int(np.ceil((max_lon + 180 - lon_offset) / lon_spacing))

            while (
                self.get_col_lon(start_col, lon_spacing, lon_offset) > min_lon + 1e-10
            ):
                start_col -= 1
            while self.get_col_lon(end_col, lon_spacing, lon_offset) < max_lon - 1e-10:
                end_col += 1

            # --- VECTORIZATION ---
            cols = np.arange(start_col, end_col + 1)
            lons = self.get_col_lon(cols, lon_spacing, lon_offset)

            xmin = lons
            ymin = lat  # Shapely will automatically broadcast this scalar
            xmax = lons + lon_spacing
            ymax = lat + self.lat_spacing

            primary_polys = shapely.box(xmin, ymin, xmax, ymax)  # pyright: ignore[reportCallIssue, reportArgumentType]
            primary_mask = shapely.intersects(primary_polys, polygon)

            # Extract only the matched column indices
            matched_cols = cols[primary_mask]

            for poly, c_idx in zip(primary_polys[primary_mask], matched_cols):
                # Generate the ESA name on the fly
                c_id = self.get_cell_name(row_idx, c_idx, lon_spacing, is_primary=True)
                cells.append(GridCell(self.D, poly, is_primary=True, cell_id=c_id))

            if self.overlap:
                over_xmin = lons + lon_spacing / 2
                over_ymin = lat + self.lat_spacing / 2
                over_xmax = over_xmin + lon_spacing
                over_ymax = over_ymin + self.lat_spacing

                overlap_polys = shapely.box(over_xmin, over_ymin, over_xmax, over_ymax)  # pyright: ignore[reportCallIssue, reportArgumentType]
                overlap_mask = shapely.intersects(overlap_polys, polygon)

                matched_over_cols = cols[overlap_mask]

                for poly, c_idx in zip(overlap_polys[overlap_mask], matched_over_cols):
                    c_id = self.get_cell_name(
                        row_idx, c_idx, lon_spacing, is_primary=False
                    )
                    cells.append(GridCell(self.D, poly, is_primary=False, cell_id=c_id))

        return cells
