"""Standalone task builder for preparing extraction tasks.

This module provides functions to prepare extraction tasks from search results,
grouping assets temporally and chunking them spatially.
"""

from __future__ import annotations

from typing import Any, Sequence, cast

import geopandas as gpd
from aereo.grid import GridCell, GridDefinition
from aereo.interfaces.core import (
    DEFAULT_CELLS_PER_TASK,
    AereoPlugin,
    ExtractionTask,
    GridConfig,
    Reprojector,
    WGS84_CRS,
    _skip_empty,
    _union_all,
)
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry

_VALID_FILTER_MODES = frozenset({"intersection", "within", "coverage"})


def _generate_cell_groups(
    assets: GeoDataFrame[AssetSchema],
    target_aoi: BaseGeometry | None,
    grid_def: Any,
    grid_config: GridConfig,
) -> list[tuple[Any, GeoDataFrame, list[GridCell]]]:
    """Group assets by start_time and generate/filter grid cells.

    Args:
        assets: GeoDataFrame of search results.
        target_aoi: Optional AOI used to clip each time group before tiling.
        grid_def: Grid definition providing ``generate_grid_cells``.
        grid_config: Grid configuration (drives filter mode and min coverage).

    Returns:
        List of ``(start_time, time_group, cells)`` tuples; entries with no
        intersecting cells or no contributing assets are omitted.

    Raises:
        ValueError: If ``grid_config.grid_filter_mode`` is not one of
            ``"intersection"``, ``"within"``, or ``"coverage"``.
    """
    profile_cell_groups: list[tuple[Any, GeoDataFrame, list[GridCell]]] = []
    grid_filter_mode = str(grid_config.grid_filter_mode).lower()
    if grid_filter_mode not in _VALID_FILTER_MODES:
        raise ValueError(
            f"Unknown grid_filter_mode: {grid_filter_mode}. "
            f"Use one of {sorted(_VALID_FILTER_MODES)}."
        )
    min_coverage = grid_config.min_coverage

    for start_time, time_group in assets.groupby("start_time"):
        group_geom = _union_all(time_group.geometry)
        if _skip_empty(group_geom):
            continue

        aoi_geom = (
            target_aoi.intersection(group_geom)
            if target_aoi is not None
            else group_geom
        )
        if _skip_empty(aoi_geom):
            continue

        all_cells = list(grid_def.generate_grid_cells(aoi_geom))
        if not all_cells:
            continue

        if grid_filter_mode != "intersection":
            all_cells = _filter_cells_by_mode(
                all_cells, aoi_geom, grid_filter_mode, min_coverage
            )
            if not all_cells:
                continue

        profile_cell_groups.append(
            (start_time, cast(GeoDataFrame, time_group), all_cells)
        )

    return profile_cell_groups


def _filter_cells_by_mode(
    cells: list[GridCell],
    aoi_geom: BaseGeometry,
    mode: str,
    min_coverage: float,
) -> list[GridCell]:
    """Filter cells by AOI coverage mode.

    Modes:
        ``"within"``: keep cells fully contained in ``aoi_geom``.
        ``"coverage"``: keep cells whose intersection with ``aoi_geom`` covers
            at least ``min_coverage`` (a fraction) of the cell.
        ``"intersection"``: caller handles this mode by skipping the filter
            entirely (all cells are kept).
    """
    if mode == "intersection":
        return list(cells)
    if mode not in _VALID_FILTER_MODES:
        raise ValueError(
            f"Unknown grid_filter_mode: {mode}. "
            f"Use one of {sorted(_VALID_FILTER_MODES)}."
        )

    filtered: list[GridCell] = []
    for cell in cells:
        cell_geom = cell.geom
        if mode == "within":
            if aoi_geom.contains(cell_geom):
                filtered.append(cell)
        elif mode == "coverage":
            intersection = cell_geom.intersection(aoi_geom)
            coverage = intersection.area / cell_geom.area if cell_geom.area > 0 else 0.0
            if coverage >= min_coverage:
                filtered.append(cell)
    return filtered


def _cache_cell_geometries(
    cell_groups: list[tuple[Any, GeoDataFrame, list[GridCell]]],
    pipeline: Sequence[AereoPlugin],
    grid_config: GridConfig,
) -> tuple[dict[GridCell, Any], dict[GridCell, BaseGeometry]]:
    """Pre-compute area_def and WGS84 geometries for all cells.

    Args:
        cell_groups: Output of :func:`_generate_cell_groups`.
        pipeline: Pipeline stages containing a potential Reprojector.
        grid_config: Grid configuration providing ``target_grid_margin``.

    Returns:
        Tuple of ``(area_def_cache, wgs84_geom_cache)`` keyed by ``GridCell``.
    """
    reprojector: Reprojector | None = None
    for plugin in pipeline:
        if isinstance(plugin, Reprojector):
            reprojector = plugin
            break

    resolution = (
        int(reprojector.resolution)
        if reprojector is not None
        else (grid_config.target_grid_dist or 10)
    )
    padding = getattr(reprojector, "padding", None) or 0
    conform_to_shape = getattr(reprojector, "conform_to", None)
    target_grid_margin = grid_config.target_grid_margin

    area_def_cache: dict[GridCell, Any] = {}
    wgs84_geom_cache: dict[GridCell, BaseGeometry] = {}

    for _, _, cells in cell_groups:
        for cell in cells:
            geobox = cell.area_def(
                resolution,
                padding,
                margin=target_grid_margin,
                conform_to=conform_to_shape,
            )
            area_def_cache[cell] = geobox
            wgs84_geom_cache[cell] = geobox.extent.to_crs(WGS84_CRS).geom

    return area_def_cache, wgs84_geom_cache


def prepare_for_extraction(
    search_results: GeoDataFrame[AssetSchema],
    grid_config: GridConfig,
    pipeline: Sequence[AereoPlugin],
    uri: str,
    target_aoi: BaseGeometry | None = None,
    cells_per_task: int = DEFAULT_CELLS_PER_TASK,
    init_params: dict[str, Any] | None = None,
) -> Sequence[ExtractionTask]:
    """Prepare extraction tasks by grouping assets and chunking grid cells.

    Groups search results by start time, generates grid cells,
    optionally filters them by AOI coverage, then chunks into tasks.

    Args:
        search_results: GeoDataFrame of assets from the search phase.
        grid_config: Tiling specification shared by all tasks.
        pipeline: Sequence of pipeline stages to execute.
        uri: Destination URI prefix for extracted artifacts.
        target_aoi: Optional geometry to clip the extraction region.
        cells_per_task: Maximum number of grid cells per task chunk.
        init_params: Optional parameters added to each task's context.

    Returns:
        A sequence of ExtractionTask objects ready for execution.

    Raises:
        ValueError: If uri is not provided or grid_dist is not set in grid_config.
    """
    grid_dist = grid_config.target_grid_dist
    if grid_dist is None:
        raise ValueError(
            "GridConfig.target_grid_dist must be an explicit integer (e.g. 50_000)."
        )

    grid_def = GridDefinition(d=grid_dist, overlap=grid_config.target_grid_overlap)

    if search_results.empty:
        return []

    cell_groups = _generate_cell_groups(
        assets=search_results,
        target_aoi=target_aoi,
        grid_def=grid_def,
        grid_config=grid_config,
    )
    if not cell_groups:
        return []

    area_def_cache, wgs84_geom_cache = _cache_cell_geometries(
        cell_groups=cell_groups,
        pipeline=pipeline,
        grid_config=grid_config,
    )

    tasks: list[ExtractionTask] = []
    for start_time, time_group, all_cells in cell_groups:
        cell_chunks = [
            all_cells[i : i + cells_per_task]
            for i in range(0, len(all_cells), cells_per_task)
        ]

        for chunk_idx, cells in enumerate(cell_chunks):
            cell_geoms = [wgs84_geom_cache[cell] for cell in cells]
            cells_union = _union_all(gpd.GeoSeries(cell_geoms))

            intersecting_mask = (
                time_group.intersects(cells_union) | time_group.geometry.isna()
            )
            chunk_assets = cast(
                GeoDataFrame[AssetSchema],
                time_group[intersecting_mask].copy(),
            )

            task_context: dict[str, Any] = {
                "chunk_id": chunk_idx,
                "total_chunks": len(cell_chunks),
                "start_time": str(start_time),
                "init_params": dict(init_params) if init_params else {},
            }

            task = ExtractionTask(
                assets=chunk_assets,
                pipeline=pipeline,
                uri=uri,
                grid_cells=cells,
                grid_config=grid_config,
                aoi=target_aoi,
                task_context=task_context,
            )
            tasks.append(task)

    return tasks
