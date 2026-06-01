"""Base Hamilton nodes for the prepare pipeline stage.

Transforms search-result assets into a sequence of :class:`ExtractionTask`
objects by generating grid cells, optionally filtering them by AOI coverage,
and chunking into task-sized batches.
"""

from __future__ import annotations

from typing import Any, Sequence, cast

import geopandas as gpd
from aereo.grid import GridCell, GridDefinition
from aereo.interfaces import ExtractionTask, GridConfig, PipelineProfile
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame as PanderaGeoDataFrame
from shapely.geometry.base import BaseGeometry

WGS84_CRS: str = "epsg:4326"
_DEFAULT_CELLS_PER_TASK: int = 50


def _skip_empty(geom: BaseGeometry | None) -> bool:
    """Return True if *geom* is None or empty."""
    return geom is None or geom.is_empty


def _union_all(geom_series: gpd.GeoSeries) -> BaseGeometry:
    """Return the union of a geometry series."""
    if hasattr(geom_series, "union_all"):
        return geom_series.union_all()
    return geom_series.unary_union


def grid_definition(grid_config: GridConfig) -> GridDefinition:
    """Create a :class:`GridDefinition` from the grid config.

    Args:
        grid_config: Tiling specification.

    Returns:
        A GridDefinition ready for cell generation.

    Raises:
        ValueError: If ``target_grid_dist`` is not set.
    """
    d = grid_config.target_grid_dist
    if d is None:
        raise ValueError("GridConfig.target_grid_dist must be set.")
    return GridDefinition(d=d, overlap=grid_config.target_grid_overlap)


def extraction_tasks(
    assets: gpd.GeoDataFrame,
    grid_config: GridConfig,
    aoi: BaseGeometry | None,
    profile: PipelineProfile,
    uri: str | None = None,
    cells_per_task: int = _DEFAULT_CELLS_PER_TASK,
) -> Sequence[ExtractionTask]:
    """Prepare extraction tasks from search assets.

    Replicates the core logic of ``Extractor.prepare_for_extraction`` as a
    Hamilton DAG node.

    Args:
        assets: GeoDataFrame of search results.
        grid_config: Tiling specification shared by all tasks.
        aoi: Optional area-of-interest geometry.
        profile: Pipeline profile defining resolution and collections.
        uri: Destination URI prefix for extracted artifacts.
        cells_per_task: Maximum grid cells per task chunk.

    Returns:
        Sequence of prepared ExtractionTask objects.

    Raises:
        ValueError: If *uri* is None or ``target_grid_dist`` is not set.
    """
    if assets is None or len(assets) == 0:
        return []

    if uri is None:
        raise ValueError("uri must be provided for task preparation.")

    grid_dist = grid_config.target_grid_dist
    if grid_dist is None:
        raise ValueError(
            "GridConfig.target_grid_dist must be an explicit integer (e.g. 50_000)."
        )

    grid_def = GridDefinition(d=grid_dist, overlap=grid_config.target_grid_overlap)
    target_grid_margin = grid_config.target_grid_margin
    grid_filter_mode = str(grid_config.grid_filter_mode).lower()
    min_coverage = grid_config.min_coverage

    resolution = int(profile.resolution)
    padding = 0
    conform_to_shape = None

    # Filter assets by profile collections if specified
    if profile.collections:
        if "collection" not in assets.columns:
            raise ValueError(
                "assets DataFrame must have a 'collection' column "
                "when profile.collections is set."
            )
        profile_assets = assets[
            assets["collection"].isin(list(profile.collections.keys()))
        ].copy()
    else:
        profile_assets = assets.copy()

    if profile_assets.empty:
        return []

    tasks: list[ExtractionTask] = []

    # Group by exact start_time
    for start_time, time_group in profile_assets.groupby("start_time"):
        group_geom = _union_all(time_group.geometry)

        if _skip_empty(group_geom):
            continue

        if aoi is not None:
            aoi_geom = aoi.intersection(group_geom)
        else:
            aoi_geom = group_geom

        if _skip_empty(aoi_geom):
            continue

        all_cells = list(grid_def.generate_grid_cells(aoi_geom))
        if not all_cells:
            continue

        # Optional grid cell filtering by asset coverage
        if grid_filter_mode != "intersection":
            filtered_cells: list[GridCell] = []
            for cell in all_cells:
                cell_geom = cell.geom
                if grid_filter_mode == "within":
                    if aoi_geom.contains(cell_geom):
                        filtered_cells.append(cell)
                elif grid_filter_mode == "coverage":
                    intersection = cell_geom.intersection(aoi_geom)
                    coverage = (
                        intersection.area / cell_geom.area
                        if cell_geom.area > 0
                        else 0.0
                    )
                    if coverage >= min_coverage:
                        filtered_cells.append(cell)
                else:
                    raise ValueError(
                        f"Unknown grid_filter_mode: {grid_filter_mode}. "
                        "Use 'intersection', 'within', or 'coverage'."
                    )
            all_cells = filtered_cells
            if not all_cells:
                continue

        # Pre-warm area_def cache
        area_def_cache: dict[GridCell, Any] = {}
        for cell in all_cells:
            area_def_cache[cell] = cell.area_def(
                resolution,
                padding,
                margin=target_grid_margin,
                conform_to=conform_to_shape,
            )

        # Chunk cells and create tasks
        cell_chunks = [
            all_cells[i : i + cells_per_task]
            for i in range(0, len(all_cells), cells_per_task)
        ]

        for chunk_idx, cells in enumerate(cell_chunks):
            cell_geoms = []
            for cell in cells:
                geobox = area_def_cache[cell]
                cell_geoms.append(geobox.extent.to_crs(WGS84_CRS).geom)

            cells_union = _union_all(gpd.GeoSeries(cell_geoms))

            intersecting_mask = (
                time_group.intersects(cells_union) | time_group.geometry.isna()
            )
            chunk_assets = cast(
                PanderaGeoDataFrame[AssetSchema],
                time_group[intersecting_mask].copy(),
            )

            if len(chunk_assets) == 0:
                continue

            task_context: dict[str, Any] = {
                "chunk_id": chunk_idx,
                "total_chunks": len(cell_chunks),
                "start_time": str(start_time),
            }

            task = ExtractionTask(
                assets=chunk_assets,
                profile=profile,  # type: ignore[arg-type]
                uri=uri,
                grid_cells=cells,
                grid_config=grid_config,
                aoi=aoi,
                task_context=task_context,
            )
            tasks.append(task)

    return tasks
