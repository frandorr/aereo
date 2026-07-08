"""Core implementation of Major TOM and ESA-compatible grid cells and definitions.

Provides GridCell and GridDefinition classes to partition geometries into cell areas
for processing, alignment, and coordinate system projection.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Callable, Sequence, cast

import attrs
import math
import geopandas as gpd
import numpy as np
import shapely
from aereo.schemas import GridSchema
from aereo.spatial import get_utm_epsg_from_geometry, reproject_geom
from majortom_eg.MajorTom import MajorTomGrid
from odc.geo.geobox import GeoBox
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry


_WGS84_CRS = "epsg:4326"
_GEOM_TOLERANCE = 1e-10
_OVERLAP_SUFFIX = "_OV"


def _expand_bounds(
    low: int,
    high: int,
    value_low: float,
    value_high: float,
    get_value: Callable[[int], float],
) -> tuple[int, int]:
    """Expand integer bounds until ``get_value`` covers the target range.

    Args:
        low: Initial lower bound.
        high: Initial upper bound.
        value_low: Target minimum coordinate value.
        value_high: Target maximum coordinate value.
        get_value: Callable returning a coordinate value for an integer index.

    Returns:
        Expanded ``(low, high)`` bounds.
    """
    tolerance = _GEOM_TOLERANCE
    while get_value(low) > value_low + tolerance:
        low -= 1
    while get_value(high) < value_high - tolerance:
        high += 1
    return low, high


def _parse_directional_value(value: str, positive: str, negative: str) -> int:
    """Parse a directional numeric string like ``"922U"`` into a signed integer."""
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
    """Calculate number of columns for a given longitude spacing."""
    return round(360 / lon_spacing) if lon_spacing > 0 else 0


def _make_cell_polygon(
    lon: float, lat: float, lon_spacing: float, lat_spacing: float
) -> Polygon:
    """Construct a cell polygon from bottom-left corner and spacings."""
    return Polygon(
        [
            [lon, lat],
            [lon + lon_spacing, lat],
            [lon + lon_spacing, lat + lat_spacing],
            [lon, lat + lat_spacing],
        ]
    )


@attrs.frozen
class GridCell:
    """A single raw MajorTOM grid cell.

    A ``GridCell`` only describes the grid geometry: its identifier, size, and
    WGS84 footprint. Extraction-specific parameters such as resolution and
    margin are provided when building a GeoBox through :meth:`to_geobox`.
    """

    id: str
    d: int
    cell_geometry: Polygon

    def to_geodataframe(self) -> GeoDataFrame[GridSchema]:
        """Convert the GridCell to a GeoDataFrame."""
        gdf = gpd.GeoDataFrame(
            {
                "grid_cell": [self.id],
                "grid_dist": [self.d],
                "cell_geometry": gpd.GeoSeries([self.cell_geometry], crs="EPSG:4326"),
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
        """UTM EPSG code for the cell's geometry."""
        return get_utm_epsg_from_geometry(self.cell_geometry)

    @property
    def utm_footprint(self) -> BaseGeometry:
        """Cell geometry reprojected to its native UTM CRS."""
        return reproject_geom(
            self.cell_geometry, src_epsg=_WGS84_CRS, dst_epsg=self.utm_crs
        )

    def area_name(self, resolution: float) -> str:
        """Get the area name based on grid cell and *resolution* in metres."""
        if isinstance(resolution, float) and resolution.is_integer():
            res_str = str(int(resolution))
        else:
            res_str = str(resolution)
        return f"{self.id}_dist-{self.d}m_res-{res_str}m"

    def to_geobox(
        self,
        resolution: float,
        margin: float = 0.0,
        alignment_resolution: float | None = None,
    ) -> GeoBox:
        """Return an odc-geo GeoBox for this cell's UTM footprint.

        The GeoBox is centred on the reprojected WGS84 centroid and its
        dimensions are an integer number of pixels, so it covers at least
        ``d * (1 + margin/100)`` metres in each direction. The centre and
        half-width are snapped to ``alignment_resolution`` (defaulting to
        ``resolution``) and the bounding box is built with ``anchor='edge'``,
        which preserves the snapped extent.

        To guarantee that nested resolutions share the same origin (e.g. VIIRS
        at 400 m and GOES at 2000 m), pass the coarser resolution as
        ``alignment_resolution`` when building the finer-resolution GeoBox. The
        half-width is then rounded up to a multiple of both resolutions, so the
        finer grid is an exact refinement of the coarser one.

        Args:
            resolution: Target pixel resolution in metres.
            margin: Percentage margin added to the patch's nominal size
                (e.g. 5.0 for 5%).
            alignment_resolution: Grid to which the centre and half-width are
                snapped. Defaults to ``resolution``. Use a coarser resolution
                when you need pixel-level alignment across nested extractions.

        Returns:
            A GeoBox aligned to the cell's UTM grid point.
        """
        utm_centroid = cast(
            Point,
            reproject_geom(
                self.cell_geometry.centroid, src_epsg=_WGS84_CRS, dst_epsg=self.utm_crs
            ),
        )

        align_res = (
            alignment_resolution if alignment_resolution is not None else resolution
        )

        # Snap the centre to the alignment grid. Using the same alignment grid
        # for different resolutions keeps origins stable.
        cx = round(utm_centroid.x / align_res) * align_res
        cy = round(utm_centroid.y / align_res) * align_res
        crs = self.utm_crs

        nominal_half = (self.d * (1 + margin / 100)) / 2
        # Round the half-width up to a multiple of both the target resolution
        # and the alignment resolution so the output shape is an integer number
        # of pixels at both resolutions.
        step = math.lcm(int(round(resolution)), int(round(align_res)))
        exact_half = math.ceil(nominal_half / step) * step

        bbox = (cx - exact_half, cy - exact_half, cx + exact_half, cy + exact_half)
        # anchor='edge' preserves the snapped bounding box instead of expanding
        # it to centre a pixel, giving deterministic origins across resolutions.
        return GeoBox.from_bbox(bbox, crs, resolution=resolution, anchor="edge")


class GridDefinition(MajorTomGrid):
    """A grid definition that generates cells intersecting a given polygon.

    Wraps ``MajorTomGrid`` to produce raw geographic cells and IDs, and is
    consumed by ``build_grid_cells`` to create ``GridCell`` instances.
    """

    def __init__(self, d: int = 10000, overlap: bool = False) -> None:
        """Initialize a grid definition.

        Args:
            d: Cell size in meters passed to ``MajorTomGrid``.
            overlap: Whether to generate half-offset overlap cells.
        """
        super().__init__(d=d, overlap=overlap)

    def _cell_from_indices(
        self,
        row_idx: int,
        col_idx: int,
        lon_spacing: float,
        is_primary: bool,
        cell_id: str,
    ) -> tuple[Polygon, str, bool]:
        """Reconstruct a raw cell from absolute row/col indices."""
        row_lat = self.get_row_lat(row_idx)
        lon_offset = self.get_lon_offset(lon_spacing)
        cell_lon = self.get_col_lon(col_idx, lon_spacing, lon_offset)

        if is_primary:
            primary = _make_cell_polygon(
                cell_lon, row_lat, lon_spacing, self.lat_spacing
            )
            return primary, cell_id, True

        half_lat = self.lat_spacing / 2
        half_lon = lon_spacing / 2
        overlap_lon = cell_lon + half_lon
        overlap_lat = row_lat + half_lat
        overlap_poly = _make_cell_polygon(
            overlap_lon, overlap_lat, lon_spacing, self.lat_spacing
        )
        return overlap_poly, cell_id, False

    def _row_id_to_index(self, y_str: str) -> int:
        rel_y = _parse_directional_value(y_str, "U", "D")
        return rel_y + int(self.row_count) // 2

    def _col_id_to_index(self, x_str: str, lat: float) -> int:
        lon_spacing = self.get_lon_spacing(lat)
        n_cols = _n_cols_for_spacing(lon_spacing)
        rel_x = _parse_directional_value(x_str, "R", "L")
        return rel_x + n_cols // 2

    def _row_index_to_id(self, row_idx: int) -> str:
        rel_y = row_idx - int(self.row_count) // 2
        return f"{abs(rel_y)}{'U' if rel_y >= 0 else 'D'}"

    def _col_index_to_id(self, col_idx: int, lon_spacing: float) -> str:
        n_cols = _n_cols_for_spacing(lon_spacing)
        rel_x = col_idx - n_cols // 2
        return f"{abs(rel_x)}{'R' if rel_x >= 0 else 'L'}"

    def raw_cell_from_id(self, cell_id: str) -> tuple[Polygon, str, bool]:
        """Return a raw cell (geom, id, is_primary) for the given cell ID."""
        if "_" not in cell_id:
            base_cell = super().cell_from_id(cell_id)
            return base_cell.geom, cell_id, base_cell.is_primary

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
        self,
        row_idx: int,
        col_idx: int,
        lon_spacing: float,
        is_primary: bool = True,
    ) -> str:
        """Build a cell identifier from row/column indices.

        Args:
            row_idx: Row index in the global grid.
            col_idx: Column index in the global grid.
            lon_spacing: Longitude spacing at the row's latitude.
            is_primary: If False, append the overlap suffix.

        Returns:
            Cell identifier such as ``"0U_0R"`` or ``"0U_0R_OV"``.
        """
        name = f"{self._row_index_to_id(row_idx)}_{self._col_index_to_id(col_idx, lon_spacing)}"
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
        cells: list[tuple[Polygon, str, bool]],
    ) -> None:
        over_xmin = lons + lon_spacing / 2
        over_ymin = lat + self.lat_spacing / 2
        over_xmax = over_xmin + lon_spacing
        over_ymax = over_ymin + self.lat_spacing

        overlap_polys = shapely.box(over_xmin, over_ymin, over_xmax, over_ymax)  # pyright: ignore[reportCallIssue, reportArgumentType]
        overlap_mask = shapely.intersects(overlap_polys, polygon)

        matched_over_cols = cols[overlap_mask]

        for poly, c_idx in zip(overlap_polys[overlap_mask], matched_over_cols):
            c_id = self.get_cell_name(row_idx, c_idx, lon_spacing, is_primary=False)
            cells.append((poly, c_id, False))

    def generate_raw_cells(
        self, polygon: BaseGeometry
    ) -> Sequence[tuple[Polygon, str, bool]]:
        """Generate raw grid cells that intersect with the given polygon."""
        shapely.prepare(polygon)
        min_lon, min_lat, max_lon, max_lat = polygon.bounds
        if min_lon > max_lon:
            max_lon += 360

        start_row = int(np.floor((min_lat + 90 - self._lat_offset) / self.lat_spacing))
        end_row = int(np.ceil((max_lat + 90 - self._lat_offset) / self.lat_spacing))

        start_row, end_row = _expand_bounds(
            start_row, end_row, min_lat, max_lat, self.get_row_lat
        )

        cells: list[tuple[Polygon, str, bool]] = []

        for row_idx in range(start_row, end_row + 1):
            lat = self.get_row_lat(row_idx)
            lon_spacing = self.get_lon_spacing(lat)
            lon_offset = self.get_lon_offset(lon_spacing)

            start_col = int(np.floor((min_lon + 180 - lon_offset) / lon_spacing))
            end_col = int(np.ceil((max_lon + 180 - lon_offset) / lon_spacing))

            start_col, end_col = _expand_bounds(
                start_col,
                end_col,
                min_lon,
                max_lon,
                lambda col: self.get_col_lon(col, lon_spacing, lon_offset),
            )

            cols = np.arange(start_col, end_col + 1)
            lons = self.get_col_lon(cols, lon_spacing, lon_offset)

            xmin = lons
            ymin = lat
            xmax = lons + lon_spacing
            ymax = lat + self.lat_spacing

            primary_polys = shapely.box(xmin, ymin, xmax, ymax)  # pyright: ignore[reportCallIssue, reportArgumentType]
            primary_mask = shapely.intersects(primary_polys, polygon)

            matched_cols = cols[primary_mask]

            for poly, c_idx in zip(primary_polys[primary_mask], matched_cols):
                c_id = self.get_cell_name(row_idx, c_idx, lon_spacing, is_primary=True)
                cells.append((poly, c_id, True))

            if self.overlap:
                self._add_overlap_cells(
                    lons, lat, lon_spacing, cols, row_idx, polygon, cells
                )

        return cells


def build_grid_cells(
    aoi: BaseGeometry,
    grid_dist: int,
) -> Sequence[GridCell]:
    """Build raw ``GridCell`` objects intersecting an AOI.

    Args:
        aoi: Area of interest geometry in WGS84.
        grid_dist: MajorTOM cell size in metres.

    Returns:
        Sequence of raw ``GridCell`` objects, one per intersecting cell.
    """
    grid_def = GridDefinition(d=grid_dist)
    return [
        GridCell(
            id=cell_id,
            d=grid_dist,
            cell_geometry=geom,
        )
        for geom, cell_id, _ in grid_def.generate_raw_cells(aoi)
    ]


def intersect_cells(
    bounds: tuple[float, float, float, float],
    grid_cells: Sequence[GridCell],
    crs: str | None = None,
) -> Sequence[GridCell]:
    """Return the grid cells from *grid_cells* that intersect *bounds*.

    Args:
        bounds: ``(minx, miny, maxx, maxy)`` bounding box.
        grid_cells: Candidate grid cells.
        crs: CRS of *bounds*. If provided, cell geometries are reprojected from
            their native WGS84 CRS to this CRS before intersection. If ``None``,
            intersection is done in WGS84.

    Returns:
        Sequence of intersecting ``GridCell`` objects.
    """
    from shapely.geometry import box as _box

    query_box = _box(*bounds)
    result: list[GridCell] = []
    for cell in grid_cells:
        geom = cell.cell_geometry
        if crs is not None:
            geom = reproject_geom(geom, src_epsg=_WGS84_CRS, dst_epsg=crs)
        if geom.intersects(query_box):
            result.append(cell)
    return result


def cells_bounds(
    cells: Iterable[GridCell],
    *,
    buffer_m: float = 0.0,
) -> tuple[float, float, float, float]:
    """Return the WGS84 bounding box of a set of grid cells.

    Args:
        cells: Grid cells to bound.
        buffer_m: Optional padding in metres around each cell. Each cell's
            UTM footprint is expanded by this amount before computing the
            overall WGS84 bounding box, so the result remains accurate even
            when cells fall in different UTM zones.

    Returns:
        A WGS84 bounding box as ``(minx, miny, maxx, maxy)``.

    Raises:
        ValueError: If *cells* is empty.
    """
    cells = list(cells)
    if not cells:
        raise ValueError("At least one GridCell is required")

    if buffer_m == 0:
        geoms = [cell.cell_geometry for cell in cells]
        return shapely.unary_union(geoms).bounds

    buffered: list[BaseGeometry] = []
    for cell in cells:
        expanded = cell.utm_footprint.buffer(buffer_m)
        buffered.append(
            reproject_geom(expanded, src_epsg=cell.utm_crs, dst_epsg=_WGS84_CRS)
        )

    return shapely.unary_union(buffered).bounds
