"""Core implementation of Major TOM and ESA-compatible grid cells and definitions.

Provides GridCell and GridDefinition classes to partition geometries into cell areas
for processing, alignment, and coordinate system projection.
"""

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

_WGS84_CRS = "epsg:4326"
_GEOM_TOLERANCE = 1e-10
_OVERLAP_SUFFIX = "_OV"


def _parse_directional_value(value: str, positive: str, negative: str) -> int:
    """Parse a directional numeric string like ``"922U"`` into a signed integer.

    Args:
        value: The string to parse (e.g. ``"922U"`` or ``"249R"``).
        positive: The character indicating a positive direction (e.g. ``"U"``).
        negative: The character indicating a negative direction (e.g. ``"D"``).

    Returns:
        Signed integer magnitude.

    Raises:
        ValueError: If the direction character is not ``positive`` or ``negative``.
    """
    magnitude = int(value[:-1])
    direction = value[-1].upper()
    if direction == positive:
        return magnitude
    if direction == negative:
        return -magnitude
    raise ValueError(
        f"Invalid direction character {direction!r} in {value!r}. "
        f"Expected {positive!r} or {negative!r}."
    )


def _n_cols_for_spacing(lon_spacing: float) -> int:
    """Calculate number of columns for a given longitude spacing.

    Args:
        lon_spacing: Longitude spacing in degrees.

    Returns:
        Number of columns around the globe.
    """
    return round(360 / lon_spacing) if lon_spacing > 0 else 0


def _make_cell_polygon(
    lon: float, lat: float, lon_spacing: float, lat_spacing: float
) -> Polygon:
    """Construct a cell polygon from bottom-left corner and spacings.

    Args:
        lon: Bottom-left longitude.
        lat: Bottom-left latitude.
        lon_spacing: Longitude extent in degrees.
        lat_spacing: Latitude extent in degrees.

    Returns:
        A Polygon representing the cell.
    """
    return Polygon(
        [
            [lon, lat],
            [lon + lon_spacing, lat],
            [lon + lon_spacing, lat + lat_spacing],
            [lon, lat + lat_spacing],
        ]
    )


class GridCell(BaseGridCell):
    """A grid cell that represents a polygon and whether it is a primary or overlapping cell.

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
        """Initialise a GridCell.

        Args:
            d: Nominal cell size in metres.
            geom: Cell polygon in WGS84.
            is_primary: Whether this is a primary (non-overlapping) cell.
            cell_id: Optional Major TOM cell ID; falls back to geohash if omitted.
        """
        super().__init__(geom=geom, is_primary=is_primary)
        self.D = d

        # Override the geohash ID from the base class if a Major TOM ID is provided
        if cell_id is not None:
            self._id = cell_id

    def to_geodataframe(self) -> GeoDataFrame[GridSchema]:
        """Convert the GridCell to a GeoDataFrame.

        Returns:
            A validated GeoDataFrame with grid cell metadata.
        """
        gdf = gpd.GeoDataFrame(
            {
                "grid_cell": [self.id()],
                "grid_dist": [self.D],
                "cell_geometry": gpd.GeoSeries([self.geom], crs="EPSG:4326"),
                "cell_utm_crs": [self.utm_crs],
                "cell_utm_footprint": gpd.GeoSeries(
                    [self.utm_footprint], crs=self.utm_crs
                ),
            },
            geometry="cell_geometry",
            crs="EPSG:4326",
        )
        return cast(GeoDataFrame, GridSchema.validate(gdf))

    @property
    def utm_crs(self) -> str:
        """UTM EPSG code for the cell's geometry.

        Returns:
            EPSG string (e.g. ``"EPSG:32701"``).
        """
        return get_utm_epsg_from_geometry(self.geom)

    @cached_property
    def utm_footprint(self) -> BaseGeometry:
        """Cell geometry reprojected to its native UTM CRS.

        Returns:
            The cell polygon in UTM coordinates.
        """
        return reproject_geom(self.geom, src_epsg=_WGS84_CRS, dst_epsg=self.utm_crs)

    def area_name(self, resolution: int) -> str:
        """Get the area name based on grid cell and a resolution in meters.

        Args:
            resolution: Resolution in meters.

        Returns:
            Area name string.
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

        Args:
            resolution: Pixel size in metres.
            padding: Extra pixels to add on all sides (uses ``GeoBox.pad``).
            margin: Percentage margin added to the nominal cell size ``self.D``
                when computing the extraction extent.  For example,
                ``margin=6.8`` produces a 10.68 km × 10.68 km box for a
                D=10 km cell (the MajorTOM Core standard).  Adjacent cells
                then overlap by design, eliminating gaps at cell edges.
            conform_to: Force a uniform ``(width, height)`` across a batch. When provided,
                ``tight=True`` is enforced internally so that every cell has the
                exact same pixel dimensions (``anchor`` is ignored in tight mode).
            **geobox_kwargs: Forwarded to ``GeoBox.from_bbox``. The default ``anchor`` is
                ``'edge'`` (top-left pixel-grid alignment).

        Returns:
            A GeoBox centred on the cell's UTM grid point.
        """
        # MajorTOM grid point in UTM — the deterministic anchor for this cell
        utm_centroid = cast(
            Point,
            reproject_geom(
                self.geom.centroid, src_epsg=_WGS84_CRS, dst_epsg=self.utm_crs
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
    """A grid definition that generates grid cells intersecting a given polygon.

    It uses shapely for efficient geometry operations and supports both primary
    and overlapping grid cells.
    """

    def __init__(self, d: int = 10000, overlap=False):
        """Initialise the GridDefinition.

        Args:
            d: The grid distance in meters (default is 10,000).
            overlap: Whether to generate overlapping grid cells.
        """
        super().__init__(d=d, overlap=overlap)

    def _cell_from_indices(
        self,
        row_idx: int,
        col_idx: int,
        lon_spacing: float,
        is_primary: bool,
        cell_id: str,
    ) -> "GridCell":
        """Reconstruct a GridCell from absolute row/col indices.

        Args:
            row_idx: Absolute row index.
            col_idx: Absolute column index.
            lon_spacing: Longitude spacing in degrees.
            is_primary: Whether this is a primary cell.
            cell_id: The cell ID string.

        Returns:
            A reconstructed GridCell.
        """
        row_lat = self.get_row_lat(row_idx)
        lon_offset = self.get_lon_offset(lon_spacing)
        cell_lon = self.get_col_lon(col_idx, lon_spacing, lon_offset)

        if is_primary:
            primary = _make_cell_polygon(
                cell_lon, row_lat, lon_spacing, self.lat_spacing
            )
            return GridCell(self.D, primary, is_primary=True, cell_id=cell_id)

        half_lat = self.lat_spacing / 2
        half_lon = lon_spacing / 2
        overlap_lon = cell_lon + half_lon
        overlap_lat = row_lat + half_lat
        overlap_poly = _make_cell_polygon(
            overlap_lon, overlap_lat, lon_spacing, self.lat_spacing
        )
        return GridCell(self.D, overlap_poly, is_primary=False, cell_id=cell_id)

    def _row_id_to_index(self, y_str: str) -> int:
        """Parse a row ID string (e.g. ``"922U"``) into an absolute row index."""
        rel_y = _parse_directional_value(y_str, "U", "D")
        return rel_y + int(self.row_count) // 2

    def _col_id_to_index(self, x_str: str, lat: float) -> int:
        """Parse a column ID string (e.g. ``"249R"``) into an absolute column index."""
        lon_spacing = self.get_lon_spacing(lat)
        n_cols = _n_cols_for_spacing(lon_spacing)
        rel_x = _parse_directional_value(x_str, "R", "L")
        return rel_x + n_cols // 2

    def _row_index_to_id(self, row_idx: int) -> str:
        """Format an absolute row index as a row ID string (e.g. ``"922U"``)."""
        rel_y = row_idx - int(self.row_count) // 2
        return f"{abs(rel_y)}{'U' if rel_y >= 0 else 'D'}"

    def _col_index_to_id(self, col_idx: int, lon_spacing: float) -> str:
        """Format an absolute column index as a column ID string (e.g. ``"249R"``)."""
        n_cols = _n_cols_for_spacing(lon_spacing)
        rel_x = col_idx - n_cols // 2
        return f"{abs(rel_x)}{'R' if rel_x >= 0 else 'L'}"

    def cell_from_id(self, cell_id: str) -> "GridCell":
        """Return a GridCell for the given cell ID.

        Supports both old geohash IDs and new ESA Major TOM naming convention.

        Args:
            cell_id: The cell ID, which can be either an old geohash or a new
                ESA Major TOM name (e.g., ``"922U_249R"`` or ``"922U_249R_OV"``).

        Returns:
            A GridCell object corresponding to the given cell ID.
        """
        # Fallback: If no underscore, route to old geohash lookup logic from majortom_eg
        if "_" not in cell_id:
            # Revert to base class method if it's an old geohash
            base_cell = super().cell_from_id(cell_id)
            return GridCell(
                self.D, base_cell.geom, base_cell.is_primary, cell_id=cell_id
            )

        parts = cell_id.split("_")
        y_str, x_str = parts[0], parts[1]
        is_primary = _OVERLAP_SUFFIX not in parts

        row_idx = self._row_id_to_index(y_str)
        row_lat = self.get_row_lat(row_idx)
        col_idx = self._col_id_to_index(x_str, row_lat)

        lon_spacing = self.get_lon_spacing(row_lat)
        return self._cell_from_indices(
            row_idx, col_idx, lon_spacing, is_primary, cell_id
        )

    def get_cell_name(
        self, row_idx: int, col_idx: int, lon_spacing: float, is_primary=True
    ) -> str:
        """Generate the ESA Major TOM naming convention (e.g., 922U_249R).

        Args:
            row_idx: The row index of the cell.
            col_idx: The column index of the cell.
            lon_spacing: The longitude spacing for the current latitude.
            is_primary: Whether this is a primary cell or an overlapping cell.

        Returns:
            The generated cell name following the ESA Major TOM convention.
        """
        name = f"{self._row_index_to_id(row_idx)}_{self._col_index_to_id(col_idx, lon_spacing)}"

        # Append an indicator for overlapping grids
        if not is_primary:
            name += f"_{_OVERLAP_SUFFIX}"

        return name

    def _add_overlap_cells(
        self,
        lons: np.ndarray,
        lat: float,
        lon_spacing: float,
        cols: np.ndarray,
        row_idx: int,
        polygon: BaseGeometry,
        cells: list[GridCell],
    ) -> None:
        """Append overlapping cells that intersect *polygon* to *cells*.

        Args:
            lons: Array of longitude values for each column.
            lat: Latitude of the current row.
            lon_spacing: Longitude spacing in degrees.
            cols: Array of column indices.
            row_idx: Current row index.
            polygon: The intersection polygon.
            cells: Mutable list of GridCell objects to append to.
        """
        over_xmin = lons + lon_spacing / 2
        over_ymin = lat + self.lat_spacing / 2
        over_xmax = over_xmin + lon_spacing
        over_ymax = over_ymin + self.lat_spacing

        overlap_polys = shapely.box(over_xmin, over_ymin, over_xmax, over_ymax)  # pyright: ignore[reportCallIssue, reportArgumentType]
        overlap_mask = shapely.intersects(overlap_polys, polygon)

        matched_over_cols = cols[overlap_mask]

        for poly, c_idx in zip(overlap_polys[overlap_mask], matched_over_cols):
            c_id = self.get_cell_name(row_idx, c_idx, lon_spacing, is_primary=False)
            cells.append(GridCell(self.D, poly, is_primary=False, cell_id=c_id))

    def generate_grid_cells(self, polygon: BaseGeometry) -> Sequence[GridCell]:
        """Generate grid cells that intersect with the given polygon.

        Processes the grid row by row, calculating the appropriate longitude
        spacing and offsets for each latitude, and uses shapely's vectorized
        geometry operations to efficiently determine which cells intersect.

        Args:
            polygon: The input polygon to intersect with the grid cells.

        Returns:
            A list of GridCell objects that intersect with the input polygon.
        """
        shapely.prepare(polygon)
        min_lon, min_lat, max_lon, max_lat = polygon.bounds
        if min_lon > max_lon:
            max_lon += 360

        start_row = int(np.floor((min_lat + 90 - self._lat_offset) / self.lat_spacing))
        end_row = int(np.ceil((max_lat + 90 - self._lat_offset) / self.lat_spacing))

        while self.get_row_lat(start_row) > min_lat + _GEOM_TOLERANCE:
            start_row -= 1
        while self.get_row_lat(end_row) < max_lat - _GEOM_TOLERANCE:
            end_row += 1

        cells: list[GridCell] = []

        # Process row by row
        for row_idx in range(start_row, end_row + 1):
            lat = self.get_row_lat(row_idx)
            lon_spacing = self.get_lon_spacing(lat)
            lon_offset = self.get_lon_offset(lon_spacing)

            start_col = int(np.floor((min_lon + 180 - lon_offset) / lon_spacing))
            end_col = int(np.ceil((max_lon + 180 - lon_offset) / lon_spacing))

            while (
                self.get_col_lon(start_col, lon_spacing, lon_offset)
                > min_lon + _GEOM_TOLERANCE
            ):
                start_col -= 1
            while (
                self.get_col_lon(end_col, lon_spacing, lon_offset)
                < max_lon - _GEOM_TOLERANCE
            ):
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
                self._add_overlap_cells(
                    lons, lat, lon_spacing, cols, row_idx, polygon, cells
                )

        return cells
