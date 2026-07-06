"""Built-in task builder plugin.

Provides the default ``build_grouped_tasks`` builder which groups search-result
assets by ``start_time`` and native ``crs`` and creates one or more
``ExtractionTask`` objects per group, chunked spatially by ``cells_per_task``.
"""

from __future__ import annotations

import shapely
from collections.abc import Sequence
from typing import Any, cast
from warnings import warn

from aereo.grid import build_grid_cells, cells_bounds
from aereo.interfaces.core import ExtractionTask
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import ConfigDict, validate_call
from shapely.geometry.base import BaseGeometry


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def build_grouped_tasks(
    search_results: GeoDataFrame[AssetSchema],
    job: ExtractionJob,
    cells_per_task: int | None = None,
    buffer_m: float = 0.0,
) -> Sequence[ExtractionTask]:
    """Build extraction tasks from *search_results* using *job* configuration.

    Assets are grouped by ``start_time`` and native ``crs``. For each group,
    the effective AOI is the intersection of the asset footprints with the
    job's ``target_aoi`` (or the asset footprints alone when no target AOI is
    configured). The AOI is tiled with the MajorTOM grid using ``job.grid_dist``
    and consecutive cells are batched into tasks of at most ``cells_per_task``
    cells.

    Args:
        search_results: GeoDataFrame of assets from the search phase.
        job: Parent ``ExtractionJob`` supplying extraction configuration.
        cells_per_task: Maximum number of MajorTOM grid cells per task.
            Defaults to ``None``, which places all grid cells for a group into
            a single task.
        buffer_m: Optional padding in metres around each chunk of grid cells.
            A value such as ``job.grid_dist * 0.1`` is useful when cropping
            assets to ensure edge pixels are included.

    Returns:
        A sequence of ``ExtractionTask`` objects ready for execution.

    Raises:
        ValueError: If ``job.output_uri`` is empty or ``cells_per_task`` is
            zero.
    """
    output_uri = job.output_uri
    if not output_uri:
        raise ValueError("ExtractionJob.output_uri must be a non-empty string.")

    if cells_per_task == 0:
        raise ValueError(
            "cells_per_task must be a positive integer, None, or negative to use all cells."
        )

    if search_results.empty:
        return []

    has_crs = "crs" in search_results.columns
    if has_crs and bool(search_results["crs"].isna().any()):
        raise ValueError(
            "assets['crs'] contains null values. "
            "Either populate crs for all assets or omit the column entirely."
        )

    if not has_crs:
        warn(
            "assets has no 'crs' column; assuming all assets share the same "
            "native CRS. Mixed-CRS assets in one task may fail or produce "
            "incorrect results.",
            UserWarning,
            stacklevel=2,
        )

    group_keys = ["start_time", "crs"] if has_crs else ["start_time"]
    target_aoi = job.effective_target_aoi

    tasks: list[ExtractionTask] = []
    for keys, group in search_results.groupby(group_keys):
        if has_crs:
            start_time, crs = keys  # type: ignore[misc]
        else:
            start_time, crs = keys, None  # type: ignore[assignment]

        group = cast(GeoDataFrame[AssetSchema], group.copy())
        group_aoi = _resolve_group_aoi(group, target_aoi)

        if group_aoi is None or group_aoi.is_empty:
            # No usable geometry/aoi to tile; keep the original job so the task
            # can still be executed with the full asset set.
            task_id = _task_id(job.name, start_time, crs, len(tasks))
            tasks.append(
                ExtractionTask(
                    id=task_id,
                    assets=group,
                    job=job,
                )
            )
            continue

        cells = build_grid_cells(aoi=group_aoi, grid_dist=job.grid_dist)
        chunk_size = (
            len(cells)
            if cells_per_task is None or cells_per_task < 0
            else cells_per_task
        )

        for chunk_index, chunk in enumerate(_chunks(cells, chunk_size)):
            chunk_bounds = cells_bounds(chunk, buffer_m=buffer_m)
            chunk_aoi = shapely.geometry.box(*chunk_bounds)

            task_id = _task_id(
                job.name,
                start_time,
                crs,
                len(tasks),
            )
            tasks.append(
                ExtractionTask(
                    id=task_id,
                    assets=group,
                    job=job,
                    aoi=chunk_aoi,
                    grid_cells=chunk,
                    task_context={
                        "chunk_index": chunk_index,
                    },
                )
            )

    return tasks


def _resolve_group_aoi(
    group: GeoDataFrame[AssetSchema],
    target_aoi: BaseGeometry | None,
) -> BaseGeometry | None:
    """Return the effective AOI for a group of assets.

    The AOI is the intersection of the group's asset footprints with the job's
    ``target_aoi``. If the job has no target AOI, the union of the asset
    footprints is used. When asset footprints are unavailable, the job's target
    AOI is returned unchanged.
    """
    if "geometry" in group.columns and not group.geometry.isna().all():
        asset_union = group.geometry.union_all()
        if not asset_union.is_empty:
            if target_aoi is not None:
                intersection = target_aoi.intersection(asset_union)
                if not intersection.is_empty:
                    return intersection
            return asset_union
    return target_aoi


def _chunks(
    items: Sequence[Any],
    chunk_size: int,
) -> Sequence[Sequence[Any]]:
    """Split *items* into consecutive chunks of size *chunk_size*."""
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _task_id(
    job_name: str,
    start_time: Any,
    crs: str | None,
    index: int,
) -> str:
    """Generate a stable task identifier."""
    time_str = str(start_time)
    crs_str = crs or "nocrs"
    return f"{job_name}_{time_str}_{crs_str}_{index}"
