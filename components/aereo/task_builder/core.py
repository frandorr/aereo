"""Standalone task builder for preparing extraction tasks.

This module provides functions to prepare extraction tasks from search results,
grouping assets temporally and chunking them spatially.
"""

from __future__ import annotations

from typing import Any, Sequence, cast

import geopandas as gpd
from aereo.grid import ExtractionPatch, GridDefinition, generate_extraction_patches
from aereo.interfaces.core import (
    DEFAULT_CELLS_PER_TASK,
    ExtractConfig,
    ExtractionTask,
    GridConfig,
    PatchConfig,
)
from aereo.pipeline import ExtractionJob
from aereo.interfaces.utils import _skip_empty, _union_all
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry

_VALID_FILTER_MODES = frozenset({"intersection", "within", "coverage"})


def _generate_patch_groups(
    assets: GeoDataFrame[AssetSchema],
    target_aoi: BaseGeometry | None,
    grid_def: Any,
    grid_config: GridConfig,
    patch_config: PatchConfig,
) -> list[tuple[Any, GeoDataFrame, list[ExtractionPatch]]]:
    """Group assets by start_time and generate/filter grid patches.

    Args:
        assets: GeoDataFrame of search results.
        target_aoi: Optional AOI used to clip each time group before tiling.
        grid_def: Grid definition used for raw partitioning.
        grid_config: Grid configuration (drives filter mode and min coverage).
        patch_config: Patch configuration (drives resolution, margin, padding, etc).

    Returns:
        List of ``(start_time, time_group, patches)`` tuples; entries with no
        intersecting patches or no contributing assets are omitted.

    Raises:
        ValueError: If ``grid_config.grid_filter_mode`` is not one of
            ``"intersection"``, ``"within"``, or ``"coverage"``.
    """
    profile_patch_groups: list[tuple[Any, GeoDataFrame, list[ExtractionPatch]]] = []
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

        all_patches = list(
            generate_extraction_patches(aoi_geom, grid_def, patch_config)
        )
        if not all_patches:
            continue

        if grid_filter_mode != "intersection":
            all_patches = _filter_patches_by_mode(
                all_patches, aoi_geom, grid_filter_mode, min_coverage
            )
            if not all_patches:
                continue

        profile_patch_groups.append(
            (start_time, cast(GeoDataFrame, time_group), all_patches)
        )

    return profile_patch_groups


def _filter_patches_by_mode(
    patches: list[ExtractionPatch],
    aoi_geom: BaseGeometry,
    mode: str,
    min_coverage: float,
) -> list[ExtractionPatch]:
    """Filter patches by AOI coverage mode.

    Modes:
        ``"within"``: keep patches fully contained in ``aoi_geom``.
        ``"coverage"``: keep patches whose intersection with ``aoi_geom`` covers
            at least ``min_coverage`` (a fraction) of the patch.
        ``"intersection"``: caller handles this mode by skipping the filter
            entirely (all patches are kept).
    """
    if mode == "intersection":
        return list(patches)
    if mode not in _VALID_FILTER_MODES:
        raise ValueError(
            f"Unknown grid_filter_mode: {mode}. "
            f"Use one of {sorted(_VALID_FILTER_MODES)}."
        )

    filtered: list[ExtractionPatch] = []
    for patch in patches:
        cell_geom = patch.cell_geometry
        if mode == "within":
            if aoi_geom.contains(cell_geom):
                filtered.append(patch)
        elif mode == "coverage":
            intersection = cell_geom.intersection(aoi_geom)
            coverage = intersection.area / cell_geom.area if cell_geom.area > 0 else 0.0
            if coverage >= min_coverage:
                filtered.append(patch)
    return filtered


def prepare_for_extraction(
    search_results: GeoDataFrame[AssetSchema],
    grid_config: GridConfig,
    patch_config: PatchConfig,
    extract: ExtractConfig,
    output_uri: str,
    target_aoi: BaseGeometry | None = None,
    cells_per_task: int = DEFAULT_CELLS_PER_TASK,
    init_params: dict[str, Any] | None = None,
    job: ExtractionJob | None = None,
) -> Sequence[ExtractionTask]:
    """Prepare extraction tasks by grouping assets and chunking grid patches.

    Groups search results by start time, generates extraction patches,
    optionally filters them by AOI coverage, then chunks into tasks.

    Args:
        search_results: GeoDataFrame of assets from the search phase.
        grid_config: Tiling specification shared by all tasks.
        patch_config: ML physical patch boundaries specification.
        extract: Declarative configuration of the extraction stages.
        output_uri: Destination URI prefix for extracted artifacts.
        target_aoi: Optional geometry to clip the extraction region.
        cells_per_task: Maximum number of patches per task chunk.
        init_params: Optional parameters added to each task's context.
        job: Optional parent ``ExtractionJob`` to attach to each task.

    Returns:
        A sequence of ExtractionTask objects ready for execution.

    Raises:
        ValueError: If output_uri is not provided or grid_dist is not set in grid_config.
    """
    grid_dist = grid_config.target_grid_dist
    if grid_dist is None:
        raise ValueError(
            "GridConfig.target_grid_dist must be an explicit integer (e.g. 50_000)."
        )

    grid_def = GridDefinition(d=grid_dist, overlap=grid_config.target_grid_overlap)

    if search_results.empty:
        return []

    patch_groups = _generate_patch_groups(
        assets=search_results,
        target_aoi=target_aoi,
        grid_def=grid_def,
        grid_config=grid_config,
        patch_config=patch_config,
    )
    if not patch_groups:
        return []

    tasks: list[ExtractionTask] = []
    for start_time, time_group, all_patches in patch_groups:
        patch_chunks = [
            all_patches[i : i + cells_per_task]
            for i in range(0, len(all_patches), cells_per_task)
        ]

        for chunk_idx, patches in enumerate(patch_chunks):
            # Extract WGS84 raw geometry for grouping mask
            patch_geoms = [patch.cell_geometry for patch in patches]
            patches_union = _union_all(gpd.GeoSeries(patch_geoms))

            intersecting_mask = (
                time_group.intersects(patches_union) | time_group.geometry.isna()
            )
            chunk_assets = cast(
                GeoDataFrame[AssetSchema],
                time_group[intersecting_mask].copy(),
            )

            task_context: dict[str, Any] = {
                "chunk_id": chunk_idx,
                "total_chunks": len(patch_chunks),
                "start_time": str(start_time),
                "init_params": dict(init_params) if init_params else {},
            }

            task = ExtractionTask(
                assets=chunk_assets,
                extract=extract,
                output_uri=output_uri,
                patches=patches,
                grid_config=grid_config,
                patch_config=patch_config,
                aoi=target_aoi,
                task_context=task_context,
                job=job,
            )
            tasks.append(task)

    return tasks
