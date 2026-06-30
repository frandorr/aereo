"""Built-in task builder plugin.

Provides the default ``build_grouped_tasks`` builder which groups search-result
assets by ``start_time`` and native ``crs`` and creates one ``ExtractionTask``
per group.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast
from warnings import warn

from aereo.interfaces.core import DEFAULT_CELLS_PER_TASK, ExtractionTask
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import ConfigDict, validate_call


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def build_grouped_tasks(
    search_results: GeoDataFrame[AssetSchema],
    job: ExtractionJob,
    cells_per_task: int = DEFAULT_CELLS_PER_TASK,
    init_params: dict[str, Any] | None = None,
) -> Sequence[ExtractionTask]:
    """Build extraction tasks from *search_results* using *job* configuration.

    Assets are grouped by ``start_time`` and native ``crs``. One
    ``ExtractionTask`` is created for each group.

    Args:
        search_results: GeoDataFrame of assets from the search phase.
        job: Parent ``ExtractionJob`` supplying extraction configuration.

    Returns:
        A sequence of ``ExtractionTask`` objects ready for execution.

    Raises:
        ValueError: If ``job.output_uri`` is empty.
    """
    output_uri = job.output_uri
    if not output_uri:
        raise ValueError("ExtractionJob.output_uri must be a non-empty string.")

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

    tasks: list[ExtractionTask] = []
    for keys, group in search_results.groupby(group_keys):
        if has_crs:
            start_time, crs = keys  # type: ignore[misc]
        else:
            start_time, crs = keys, None  # type: ignore[assignment]

        group = cast(GeoDataFrame[AssetSchema], group.copy())
        task_id = _task_id(job.name, start_time, crs, len(tasks))
        tasks.append(
            ExtractionTask(
                id=task_id,
                assets=group,
                job=job,
            )
        )

    return tasks


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
