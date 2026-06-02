"""Standalone task builder for preparing extraction tasks.

This module replaces the legacy ``Extractor.prepare_for_extraction`` plugin
method with a pure function that can be called directly by the client.
"""

from __future__ import annotations

from typing import Any, Sequence, cast

import geopandas as gpd
from aereo.grid import GridCell
from aereo.interfaces.core import (
    DEFAULT_CELLS_PER_TASK,
    ExtractionTask,
    GridConfig,
    WGS84_CRS,
    _skip_empty,
    _union_all,
)
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry


def _filter_assets_by_profile(
    search_results: GeoDataFrame[AssetSchema],
    profile: Any,
) -> GeoDataFrame[AssetSchema]:
    """Filter search results to assets matching *profile.collections*."""
    if hasattr(profile, "collections") and profile.collections:
        filtered = search_results[
            search_results["collection"].isin(list(profile.collections.keys()))
        ].copy()
    else:
        filtered = search_results.copy()
    return cast(GeoDataFrame[AssetSchema], filtered)


def _generate_cell_groups(
    profile_assets: GeoDataFrame[AssetSchema],
    target_aoi: BaseGeometry | None,
    grid_def: Any,
    grid_config: GridConfig,
) -> list[tuple[Any, GeoDataFrame, list[GridCell]]]:
    """Group assets by start_time and generate/filter grid cells."""
    profile_cell_groups: list[tuple[Any, GeoDataFrame, list[GridCell]]] = []
    grid_filter_mode = str(grid_config.grid_filter_mode).lower()
    min_coverage = grid_config.min_coverage

    for start_time, time_group in profile_assets.groupby("start_time"):
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
    """Filter cells by coverage mode ('within' or 'coverage')."""
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
        else:
            raise ValueError(
                f"Unknown grid_filter_mode: {mode}. "
                f"Use 'intersection', 'within', or 'coverage'."
            )
    return filtered


def _cache_cell_geometries(
    cell_groups: list[tuple[Any, GeoDataFrame, list[GridCell]]],
    profile: Any,
    grid_config: GridConfig,
) -> tuple[dict[GridCell, Any], dict[GridCell, BaseGeometry]]:
    """Pre-compute area_def and WGS84 geometries for all cells.

    Returns:
        Tuple of (area_def_cache, wgs84_geom_cache).
    """
    resolution = int(profile.resolution)
    padding = getattr(profile, "padding", None) or 0
    conform_to_shape = getattr(profile, "conform_to", None)
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


def _prepare_profile_tasks(
    search_results: GeoDataFrame[AssetSchema],
    profile: Any,
    grid_def: Any,
    grid_config: GridConfig,
    target_aoi: BaseGeometry | None,
    uri: str,
    cells_per_task: int,
    init_params: dict[str, Any] | None,
) -> list[ExtractionTask]:
    """Prepare tasks for a single profile."""
    profile_assets = _filter_assets_by_profile(search_results, profile)
    if profile_assets.empty:
        return []

    cell_groups = _generate_cell_groups(
        profile_assets=profile_assets,
        target_aoi=target_aoi,
        grid_def=grid_def,
        grid_config=grid_config,
    )
    if not cell_groups:
        return []

    area_def_cache, wgs84_geom_cache = _cache_cell_geometries(
        cell_groups=cell_groups,
        profile=profile,
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
                profile=profile,
                uri=uri,
                grid_cells=cells,
                grid_config=grid_config,
                aoi=target_aoi,
                task_context=task_context,
            )
            tasks.append(task)

    return tasks


def prepare_for_extraction(
    search_results: GeoDataFrame[AssetSchema],
    grid_config: GridConfig,
    profiles: Sequence[Any],
    uri: str,
    target_aoi: BaseGeometry | None = None,
    cells_per_task: int = DEFAULT_CELLS_PER_TASK,
    init_params: dict[str, Any] | None = None,
) -> Sequence[ExtractionTask]:
    """Prepare extraction tasks by grouping assets and chunking grid cells.

    Groups search results by profile and start time, generates grid cells,
    optionally filters them by AOI coverage, then chunks into tasks.

    Args:
        search_results: GeoDataFrame of assets from the search phase.
        grid_config: Tiling specification shared by all tasks.
        profiles: Profiles defining what to extract. Must contain at least one.
        uri: Destination URI prefix for extracted artifacts.
        target_aoi: Optional geometry to clip the extraction region.
        cells_per_task: Maximum number of grid cells per task chunk.
        init_params: Optional parameters added to each task's context.

    Returns:
        A sequence of ExtractionTask objects ready for execution.

    Raises:
        ValueError: If uri is not provided, no profiles are provided, or
            grid_dist is not set in grid_config.
    """
    if not profiles:
        raise ValueError(
            "prepare_for_extraction requires at least one profile to be defined."
        )

    grid_dist = grid_config.target_grid_dist
    if grid_dist is None:
        raise ValueError(
            "GridConfig.target_grid_dist must be an explicit integer (e.g. 50_000)."
        )

    from aereo.grid import GridDefinition

    grid_def = GridDefinition(d=grid_dist, overlap=grid_config.target_grid_overlap)

    tasks: list[ExtractionTask] = []
    for profile in profiles:
        profile_tasks = _prepare_profile_tasks(
            search_results=search_results,
            profile=profile,
            grid_def=grid_def,
            grid_config=grid_config,
            target_aoi=target_aoi,
            uri=uri,
            cells_per_task=cells_per_task,
            init_params=init_params,
        )
        tasks.extend(profile_tasks)

    return tasks
