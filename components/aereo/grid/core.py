from functools import cached_property
from typing import Any, Sequence, cast

import geopandas as gpd
import numpy as np
import shapely
from aereo.schemas import GridSchema
from aereo.spatial import get_utm_epsg_from_geometry, reproject_geom
from majortom_eg.MajorTom import GridCell as BaseGridCell
from majortom_eg.MajorTom import MajorTomGrid
from odc.geo.geobox import GeoBox
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry


class GridCell(BaseGridCell):
    """
    A grid cell that represents a polygon and whether it is a primary or overlapping cell.

    ``area_def()`` returns an :class:`odc.geo.geobox.GeoBox` centred on the
    cell's grid point with a fixed size of ``D * (1 + margin/100)`` metres.
    Use ``area_name()`` when you need a human-readable identifier
    for the cell at a given resolution.
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

    def area_name(self, resolution: int) -> str:
        """
        Get the area name based on grid cell and a resolution in meters.
        Args:
            resolution (int): Resolution in meters
        Returns:
            str: Area name

        """
        return f"{self.id()}_dist-{self.D}m_res-{resolution}m"

    def area_def(
        self,
        resolution: int,
        padding: int = 0,
        margin: float = 0.0,
        conform_to: tuple[int, int] | None = None,
        **geobox_kwargs: Any,
    ) -> GeoBox:
        """Return an odc-geo GeoBox for this cell's UTM footprint.

        The extent is a fixed-size square centred on the MajorTOM grid point
        (the WGS84 centroid reprojected to UTM).  This guarantees that
        extractions of the same cell from different scenes align pixel-wise,
        and that neighbouring cells overlap slightly when ``margin > 0``.

        Parameters
        ----------
        resolution:
            Pixel size in metres.
        padding:
            Extra pixels to add on all sides (uses ``GeoBox.pad``).
        margin:
            Percentage margin added to the nominal cell size ``self.D``
            when computing the extraction extent.  For example,
            ``margin=6.8`` produces a 10.68 km × 10.68 km box for a
            D=10 km cell (the MajorTOM Core standard).  Adjacent cells
            then overlap by design, eliminating gaps at cell edges.
        conform_to:
            Force a uniform ``(width, height)`` across a batch. When provided,
            ``tight=True`` is enforced internally so that every cell has the
            exact same pixel dimensions (``anchor`` is ignored in tight mode).
        **geobox_kwargs:
            Forwarded to ``GeoBox.from_bbox``. The default ``anchor`` is
            ``'edge'`` (top-left pixel-grid alignment).
        """
        # MajorTOM grid point in UTM — the deterministic anchor for this cell
        utm_centroid = cast(
            Point,
            reproject_geom(
                self.geom.centroid, src_epsg="epsg:4326", dst_epsg=self.utm_crs
            ),
        )
        # Snap centre to the resolution grid so that pixel edges are
        # deterministic and identical across all cells at the same resolution.
        cx = round(utm_centroid.x / resolution) * resolution
        cy = round(utm_centroid.y / resolution) * resolution
        crs = self.utm_crs

        if conform_to is not None:
            target_w, target_h = conform_to
            half_w = (target_w * resolution) / 2
            half_h = (target_h * resolution) / 2
            bbox = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
            geobox = GeoBox.from_bbox(
                bbox,
                crs,
                resolution=resolution,
                tight=True,
            )
        else:
            geobox_kwargs.setdefault("anchor", "edge")
            half = (self.D * (1 + margin / 100)) / 2
            bbox = (cx - half, cy - half, cx + half, cy + half)
            geobox = GeoBox.from_bbox(bbox, crs, resolution=resolution, **geobox_kwargs)

        if padding:
            geobox = geobox.pad(padding)

        return geobox


class GridDefinition(MajorTomGrid):
    """
    A grid definition that generates grid cells intersecting a given polygon.
    It uses shapely for efficient geometry operations and supports both primary and overlapping grid cells.
    """

    def __init__(self, d: int = 10000, overlap=False):
        """
        Initializes the GridDefinition with the specified grid distance and overlap option.
        Args:
            d (int): The grid distance in meters (default is 10,000).
            overlap (bool): Whether to generate overlapping grid cells (default is False).
        """
        super().__init__(d=d, overlap=overlap)

    def cell_from_id(self, cell_id: str) -> GridCell:
        """
        Overrides the base class method to support both old geohash IDs and new ESA Major TOM naming convention.

        Args:
            cell_id (str): The cell ID, which can be either an old geohash or a new ESA Major TOM name (e.g., "922U_249R" or "922U_249R_OV").
        Returns:
            GridCell: A GridCell object corresponding to the given cell ID.
        """
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

    def get_cell_name(
        self, row_idx: int, col_idx: int, lon_spacing: float, is_primary=True
    ) -> str:
        """Generates the ESA Major TOM naming convention (e.g., 922D_249L).

        Args:
            row_idx (int): The row index of the cell.
            col_idx (int): The column index of the cell.
            lon_spacing (float): The longitude spacing for the current latitude.
            is_primary (bool): Whether this is a primary cell or an overlapping cell.
        Returns:
            str: The generated cell name following the ESA Major TOM convention.
        """
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
        """
        Generates grid cells that intersect with the given polygon. It processes the grid row by row,
        calculating the appropriate longitude spacing and offsets for each latitude, and uses shapely's vectorized
        geometry operations to efficiently determine which cells intersect the polygon.

        Args:
            polygon (BaseGeometry): The input polygon to intersect with the grid cells.
        Returns:
            Sequence[GridCell]: A list of GridCell objects that intersect with the input polygon.

        """
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

    def max_shape(
        self,
        cells: Sequence[GridCell],
        resolution: int,
        padding: int = 0,
        margin: float = 0.0,
        **geobox_kwargs: Any,
    ) -> tuple[int, int]:
        """Return the maximum (width, height) in pixels across *cells*.

        This is the shape you pass to ``GridCell.area_def(..., conform_to=...)``
        when you want every cell in the batch to share an identical tensor shape.

        Args:
            cells: Sequence of GridCell objects to evaluate.
            resolution: Pixel size in metres.
            padding: Number of extra pixels added on each side (same semantics as
                :meth:`GridCell.area_def`).
            margin: Percentage margin added to ``self.D`` (same semantics as
                :meth:`GridCell.area_def`).
            **geobox_kwargs: Forwarded to :meth:`GridCell.area_def`.

        Returns:
            Tuple of ``(max_width, max_height)`` in pixels.
        """
        shapes = [
            cell.area_def(resolution, padding=0, margin=margin, **geobox_kwargs).shape
            for cell in cells
        ]
        max_w = max((s.x for s in shapes), default=0)
        max_h = max((s.y for s in shapes), default=0)
        if padding:
            max_w += 2 * padding
            max_h += 2 * padding
        return max_w, max_h

    def to_esa_compatible_dataframe(self, cells: Sequence[GridCell]) -> GeoDataFrame:
        """
        Converts a sequence of GridCells into a GeoDataFrame that perfectly
        matches the schema and formatting of the original ESA `Grid.points` dataframe.

        Args:
            cells (Sequence[GridCell]): A list of GridCell objects to convert.
        Returns:
            GeoDataFrame: A GeoDataFrame with columns and formatting identical to the ESA grid points.
        """

        data = {
            "name": [],
            "row": [],
            "col": [],
            "row_idx": [],
            "col_idx": [],
            "utm_zone": [],
            "epsg": [],
        }
        geometries = []

        for cell in cells:
            # ESA's base grid dataframe only stored primary grid points, not overlaps
            if not cell.is_primary:
                continue

            parts = cell.id().split("_")
            r_str, c_str = parts[0], parts[1]

            # ESA grid points are defined as the bottom-left corner of the cell
            bottom_left = cell.geom.exterior.coords[0]
            lon, lat = bottom_left[0], bottom_left[1]

            # Reconstruct original ESA row_idx and col_idx
            y_val = int(r_str[:-1])
            rel_y = y_val if r_str[-1].upper() == "U" else -y_val
            row_idx = rel_y + int(self.row_count) // 2

            lon_spacing = self.get_lon_spacing(lat)
            n_cols = round(360 / lon_spacing) if lon_spacing > 0 else 0
            x_val = int(c_str[:-1])
            rel_x = x_val if c_str[-1].upper() == "R" else -x_val
            col_idx = rel_x + n_cols // 2

            # Format the CRS to match ESA exactly (e.g., 'EPSG:32701' and '32701')
            raw_crs = str(cell.utm_crs).upper()
            epsg_str = raw_crs if "EPSG:" in raw_crs else f"EPSG:{raw_crs}"
            utm_zone = epsg_str.split(":")[-1]

            data["name"].append(cell.id())
            data["row"].append(r_str)
            data["col"].append(c_str)
            data["row_idx"].append(row_idx)
            data["col_idx"].append(col_idx)
            data["utm_zone"].append(utm_zone)
            data["epsg"].append(epsg_str)

            geometries.append(Point(lon, lat))

        # Return a GeoDataFrame with the exact same structure as the ESA one
        return cast(
            GeoDataFrame, gpd.GeoDataFrame(data, geometry=geometries, crs="EPSG:4326")
        )
