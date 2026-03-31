from functools import lru_cache
from pathlib import Path
from typing import cast

import geopandas as gpd
from aer.repository.core import AerSpatialRepository
from aer.spatial import GridCell, GridDefinition, OverlapMode
from aer.spatial.majortom import Grid
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from structlog import get_logger

logger = get_logger(__name__)


class AerParquetSpatialRepository(AerSpatialRepository):
    def __init__(self, grid_store: Path | str):
        super().__init__()
        self.grid_store = (
            grid_store if isinstance(grid_store, Path) else Path(grid_store)
        )

    @lru_cache(maxsize=2)
    def _load_grid(self, grid_def: GridDefinition):
        grid_name = grid_def.name
        grid_path = self.grid_store / f"{grid_name}.parquet"
        if not grid_path.exists():
            logger.info(f"Grid file not found at {grid_path}. Creating new grid.")
            self._create_grid(grid_def, self.grid_store)
        return gpd.read_parquet(grid_path)

    def _create_grid(self, grid_def: GridDefinition, grid_store: Path | str):
        grid_name = grid_def.name
        grid_path = (
            grid_store if isinstance(grid_store, Path) else Path(grid_store)
        ) / f"{grid_name}.parquet"
        if grid_path.exists():
            raise FileExistsError(
                f"Grid file already exists: {grid_path}. "
                "Consider deleting the existing file or using a different grid name."
            )
        extent = grid_def.extent
        latitude_range = (extent[1], extent[3])
        longitude_range = (extent[0], extent[2])
        grid = Grid(
            name=grid_name,
            dist=grid_def.dist,
            latitude_range=latitude_range,
            longitude_range=longitude_range,
            utm_definition=grid_def.utm_definition,
        )
        grid.save_to_parquet(output_path=grid_path)

    def get_grid_cells(
        self,
        grid_def: GridDefinition,
        geometry: BaseGeometry | None = None,
        overlap_mode: OverlapMode | None = None,
    ) -> list[GridCell]:
        grid_gdf = self._load_grid(grid_def)
        if geometry is not None and overlap_mode is not None:
            if overlap_mode == OverlapMode.INTERSECTS:
                grid_gdf = grid_gdf[grid_gdf.intersects(geometry)]
            elif overlap_mode == OverlapMode.CONTAINS:
                grid_gdf = grid_gdf[grid_gdf.contains(geometry)]
            elif overlap_mode == OverlapMode.WITHIN:
                grid_gdf = grid_gdf[grid_gdf.within(geometry)]
            else:
                raise ValueError(f"Unsupported overlap mode: {overlap_mode}")
        return [
            GridCell(
                grid_cell=cast(str, row["grid_cell"]),
                footprint=cast(Polygon, row["geometry"]),
                utm_footprint=cast(Polygon, row["utm_footprint"]),
                utm_crs=cast(str, row["utm_crs"]),
                dist=cast(int, row["dist"]),
            )
            for _, row in grid_gdf.iterrows()
        ]
