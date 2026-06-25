"""Executor abstraction for running extraction tasks.

Defines the :class:`Executor` protocol and a local implementation that
wraps :func:`aereo.execution.run_task` with caching, failure handling, and
optional parallelism.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Literal, Protocol, cast

import geopandas as gpd
import pandas as pd
from structlog import get_logger

from aereo.cache import TaskResultCache
from aereo.execution import run_task
from aereo.interfaces import ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame

logger = get_logger()

_STRICT_MODE = "strict"
_BEST_EFFORT_MODE = "best_effort"


class Executor(Protocol):
    """Protocol for pluggable task executors.

    An executor turns a sequence of :class:`ExtractionTask` objects into a
    single validated artifact GeoDataFrame.
    """

    def __call__(
        self,
        tasks: Sequence[ExtractionTask],
    ) -> GeoDataFrame[ArtifactSchema]:
        """Execute *tasks* and return their artifacts."""
        ...


def _run_single_task(
    task: ExtractionTask,
    cache: TaskResultCache | None,
) -> GeoDataFrame[ArtifactSchema]:
    """Run a single task, respecting the cache.

    Args:
        task: The extraction task to execute.
        cache: Optional per-task artifact catalog cache.

    Returns:
        A ``GeoDataFrame[ArtifactSchema]`` with the task's artifacts.
    """
    if cache is not None and not task.job.overwrite:
        cached = cache.load(task)
        if cached is not None:
            return cached

    artifacts = run_task(task)

    if cache is not None:
        cache.save(task, artifacts)

    return artifacts


class LocalExecutor:
    """Execute extraction tasks locally.

    Wraps :func:`aereo.execution.run_task` with optional caching, failure
    handling, and local parallelism through process or thread pools.
    """

    def __init__(
        self,
        workers: int | None = 1,
        failure_mode: Literal["strict", "best_effort"] = _STRICT_MODE,
        cache: TaskResultCache | None = None,
        use_threads: bool = False,
    ) -> None:
        """Create a new LocalExecutor.

        Args:
            workers: Maximum number of parallel workers. ``None`` or ``1`` runs
                tasks sequentially in the current process. ``>1`` dispatches
                tasks through a process or thread pool.
            failure_mode: ``"strict"`` aborts on the first failed task;
                ``"best_effort"`` skips failed tasks and returns successful ones.
            cache: Optional per-task artifact catalog cache.
            use_threads: When ``True`` and *workers* > 1, use a
                :class:`ThreadPoolExecutor` instead of a
                :class:`ProcessPoolExecutor`.
        """
        self.workers = workers
        self.failure_mode = failure_mode
        self.cache = cache
        self.use_threads = use_threads

    def __call__(self, tasks: Sequence[ExtractionTask]) -> GeoDataFrame[ArtifactSchema]:
        """Execute *tasks* and return a unified artifact GeoDataFrame.

        Args:
            tasks: Extraction tasks to run.

        Returns:
            A validated ``GeoDataFrame[ArtifactSchema]``.
        """
        if not tasks:
            return cast(
                GeoDataFrame[ArtifactSchema], ArtifactSchema.empty_geodataframe()
            )

        if self.workers is None or self.workers == 1 or len(tasks) == 1:
            results = self._run_sequential(tasks)
        else:
            results = self._run_parallel(tasks)

        if not results:
            return cast(
                GeoDataFrame[ArtifactSchema], ArtifactSchema.empty_geodataframe()
            )

        return cast(
            GeoDataFrame[ArtifactSchema],
            gpd.GeoDataFrame(
                pd.concat(results, ignore_index=True), geometry="geometry"
            ),
        )

    def _run_sequential(
        self,
        tasks: Sequence[ExtractionTask],
    ) -> list[GeoDataFrame[ArtifactSchema]]:
        """Run tasks sequentially, applying failure mode."""
        results: list[GeoDataFrame[ArtifactSchema]] = []
        for idx, task in enumerate(tasks):
            try:
                results.append(_run_single_task(task, self.cache))
            except Exception as exc:
                if self.failure_mode == _STRICT_MODE:
                    raise
                logger.warning(
                    "task_failed_best_effort",
                    task_index=idx,
                    error=str(exc),
                )
        return results

    def _run_parallel(
        self,
        tasks: Sequence[ExtractionTask],
    ) -> list[GeoDataFrame[ArtifactSchema]]:
        """Run tasks through a process or thread pool, applying failure mode."""
        executor_cls = ThreadPoolExecutor if self.use_threads else ProcessPoolExecutor
        results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * len(tasks)

        with executor_cls(max_workers=self.workers) as executor:
            futures = {
                executor.submit(_run_single_task, task, self.cache): i
                for i, task in enumerate(tasks)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    if self.failure_mode == _STRICT_MODE:
                        for pending in futures:
                            pending.cancel()
                        raise
                    logger.warning(
                        "task_failed_best_effort",
                        task_index=idx,
                        error=str(exc),
                    )

        return [r for r in results if r is not None]
