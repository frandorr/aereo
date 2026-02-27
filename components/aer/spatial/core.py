import attrs
import geopandas as gpd
from functools import cached_property
from shapely.geometry import Polygon
from pyresample.geometry import AreaDefinition
from aer.settings import ENV_SETTINGS
from pyproj import Proj, Transformer
from shapely.ops import transform


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
    # Define a projection that converts lat/lon to a metric system (e.g., UTM)
    proj = Proj(dst_epsg)

    # Create a transformer to convert lat/lon to UTM
    transformer = Transformer.from_crs(src_epsg, proj.to_proj4(), always_xy=True)

    # Transform the polygon to the UTM coordinate system
    projected_polygon = transform(transformer.transform, polygon)

    return projected_polygon


@attrs.frozen
class GridCell:
    row: str
    col: str
    dist: int
    bounds: Polygon
    epsg: str

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
    grid_cells: frozenset[GridCell]

    def intersects(self, other: "GridSpatialExtent") -> bool:
        return not self.grid_cells.isdisjoint(other.grid_cells)

    def intersection(self, other: "GridSpatialExtent") -> "GridSpatialExtent":
        return GridSpatialExtent(self.grid_cells & other.grid_cells)


@attrs.frozen
class GridDefinition:
    name: str
    dist: int

    @cached_property
    def grid(self) -> gpd.GeoDataFrame:
        """Load grid points from a parquet file.

        Returns:
            gpd.GeoDataFrame: Grid points.
        Raises:
            ValueError: If the grid file is empty.
        """
        # check path exists
        grid_path = (
            ENV_SETTINGS.GRID_STORE_PATH / f"grid_{self.name}_{self.dist}km.parquet"
        )
        gdf = gpd.read_parquet(grid_path)  # pyright: ignore[reportUnknownMemberType]
        if gdf.empty:
            raise ValueError(f"Grid file at {grid_path} is cached_propertyempty.")
        return gdf

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
