"""Local execution backends for AEREO extraction tasks."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Iterable, Optional, Sequence

from aereo.backends.core import TaskRunner
from aereo.interfaces import ExecutionBackend, ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()


class LocalProcessBackend(ExecutionBackend):
    """Execute tasks locally using sequential or process-based parallelism.

    When *max_workers* is ``None`` or there is only one task, execution is
    sequential. Otherwise a :class:`ProcessPoolExecutor` is used.
    """

    def __init__(self, max_workers: int | None = None) -> None:
        """Create a new local process backend.

        Args:
            max_workers: Maximum number of worker processes. ``None`` disables
                parallelism and runs tasks sequentially.
        """
        self.max_workers = max_workers

    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: Optional[TaskRunner] = None,
    ) -> Iterable[GeoDataFrame[ArtifactSchema]]:
        """Execute *tasks* using local process-based parallelism.

        Args:
            tasks: Extraction tasks to run.
            runner: TaskRunner that resolves and executes each task.

        Returns:
            An iterable of ``GeoDataFrame[ArtifactSchema]`` results, one per task,
            in the same order as *tasks*.

        Raises:
            ValueError: If *runner* is ``None``.
        """

        if runner is None:
            raise ValueError("LocalProcessBackend requires a runner")
        if not tasks:
            return []

        if self.max_workers is None or len(tasks) == 1:
            return [runner.run(t) for t in tasks]

        results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * len(tasks)
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(runner.run, task): i for i, task in enumerate(tasks)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.error(
                        "local_task_failed",
                        task_index=idx,
                        error=str(exc),
                    )
                    raise

        return [r for r in results if r is not None]


class ThreadBackend(ExecutionBackend):
    """Execute tasks locally using thread-based parallelism.

    This backend is ideal for **I/O-bound** extractors (e.g. those that spend
    most of their time waiting on HTTP requests for COG tiles). Because
    threads share memory, there is no pickling overhead and no need for
    extractors to be serialisable across process boundaries.

    When *max_workers* is ``None`` or there is only one task, execution is
    sequential. Otherwise a :class:`ThreadPoolExecutor` is used.
    """

    def __init__(self, max_workers: int | None = None) -> None:
        """Create a new thread-based backend.

        Args:
            max_workers: Maximum number of worker threads. ``None`` disables
                parallelism and runs tasks sequentially.
        """
        self.max_workers = max_workers

    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: Optional[TaskRunner] = None,
    ) -> Iterable[GeoDataFrame[ArtifactSchema]]:
        """Execute *tasks* using local thread-based parallelism.

        Args:
            tasks: Extraction tasks to run.
            runner: TaskRunner that resolves and executes each task.

        Returns:
            An iterable of ``GeoDataFrame[ArtifactSchema]`` results, one per task,
            in the same order as *tasks*.

        Raises:
            ValueError: If *runner* is ``None``.
        """

        if runner is None:
            raise ValueError("ThreadBackend requires a runner")
        if not tasks:
            return []

        if self.max_workers is None or len(tasks) == 1:
            return [runner.run(t) for t in tasks]

        results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * len(tasks)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(runner.run, task): i for i, task in enumerate(tasks)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.error(
                        "thread_task_failed",
                        task_index=idx,
                        error=str(exc),
                    )
                    raise

        return [r for r in results if r is not None]
