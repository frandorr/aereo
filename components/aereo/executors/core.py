"""Executor abstraction for running extraction tasks.

Defines the :class:`Executor` protocol and a local implementation that
wraps :func:`aereo.execution.run_task` with caching, failure handling, and
optional parallelism.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal, Protocol, cast

import geopandas as gpd
import pandas as pd
from joblib import Parallel, delayed
from structlog import get_logger

from aereo.execution import run_task
from aereo.interfaces import ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame

if TYPE_CHECKING:
    from aereo.cache import TaskResultCache

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


class _TaskOutcome:
    """Result or error from running a single task in a worker."""

    def __init__(
        self,
        idx: int,
        artifacts: GeoDataFrame[ArtifactSchema] | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.idx = idx
        self.artifacts = artifacts
        self.error = error


def _run_single_task_indexed(
    idx: int,
    task: ExtractionTask,
    cache: TaskResultCache | None,
) -> _TaskOutcome:
    """Run a task and return a picklable outcome object.

    Returning the exception object instead of raising lets ``joblib.Parallel``
    finish the rest of the batch in ``best_effort`` mode, while ``strict`` mode
    can re-raise the original exception in the parent process.
    """
    try:
        return _TaskOutcome(idx=idx, artifacts=_run_single_task(task, cache))
    except BaseException as exc:  # noqa: BLE001
        return _TaskOutcome(idx=idx, error=exc)


class LocalExecutor:
    """Execute extraction tasks locally.

    Wraps :func:`aereo.execution.run_task` with optional caching, failure
    handling, and local parallelism through ``joblib``.

    By default ``joblib``'s ``loky`` backend is used for process-based
    parallelism. ``loky`` starts clean interpreter processes, which avoids the
    fork-after-read deadlock that happens when worker processes inherit
    netCDF/HDF5 state from the parent.
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
                tasks through a joblib pool. If -1 is passed, the number of
                workers is set to the number of CPUs in the system.
            failure_mode: ``"strict"`` aborts on the first failed task;
                ``"best_effort"`` skips failed tasks and returns successful ones.
            cache: Optional per-task artifact catalog cache.
            use_threads: When ``True`` and *workers* > 1, use joblib's
                ``threading`` backend instead of ``loky``. Not recommended:
                threads share native library state (e.g. netCDF/HDF5 readers),
                which can deadlock or corrupt reads. Prefer the default
                process-based backend (``loky``) that uses separate cores.
        """
        self.workers = workers
        if self.workers == -1:
            import multiprocessing

            self.workers = multiprocessing.cpu_count()
        self.failure_mode = failure_mode
        self.cache = cache
        self.use_threads = use_threads
        self._ran_parallel = False
        if self.use_threads and self.workers is not None and self.workers > 1:
            logger.warning(
                "threads_backend_not_recommended",
                message=(
                    "use_threads=True runs tasks in a shared thread pool. "
                    "Native libraries used to read formats like netCDF/HDF5 "
                    "(.nc) are not thread-safe and can deadlock or hang. "
                    "Prefer the default process-based backend (cores) by "
                    "leaving use_threads=False."
                ),
            )

    def shutdown(self, _wait: bool = True) -> None:
        """Release memory retained after task execution.

        Two retention sources are addressed:

        * The current process: freed arrays are not returned to the OS by
          glibc's allocator, so RSS stays at its high-water mark. A
          ``gc.collect()`` followed by ``malloc_trim(0)`` returns them.
        * ``joblib``'s reusable ``loky`` pool: idle workers stay alive after
          a parallel batch, each keeping its high-water RSS. If this executor
          dispatched parallel work, the pool is terminated; the next parallel
          run spawns fresh workers. Note the pool is process-global, so this
          also affects other joblib users in the same process.
        """
        import ctypes
        import gc

        gc.collect()
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except OSError:
            pass  # non-glibc platform (e.g. musl, macOS)

        if self._ran_parallel and not self.use_threads:
            from joblib.externals.loky import get_reusable_executor

            get_reusable_executor().shutdown(wait=_wait, kill_workers=True)
        return None

    def __enter__(self) -> LocalExecutor:
        return self

    def __exit__(self, *_exc: object) -> Literal[False]:
        self.shutdown()
        return False

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

        if self.workers is None or self.workers == 1:
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
        """Run tasks through joblib, applying failure mode."""
        backend = "threading" if self.use_threads else "loky"
        self._ran_parallel = True
        outcomes = cast(
            list[_TaskOutcome],
            Parallel(n_jobs=self.workers, backend=backend)(
                delayed(_run_single_task_indexed)(idx, task, self.cache)
                for idx, task in enumerate(tasks)
            ),
        )

        results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * len(tasks)
        for outcome in outcomes:
            if outcome.error is not None:
                if self.failure_mode == _STRICT_MODE:
                    raise outcome.error
                logger.warning(
                    "task_failed_best_effort",
                    task_index=outcome.idx,
                    error=str(outcome.error),
                )
            else:
                results[outcome.idx] = outcome.artifacts

        return [r for r in results if r is not None]
