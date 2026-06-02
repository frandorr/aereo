"""Local execution backends for AEREO extraction tasks."""

from __future__ import annotations

from concurrent.futures import (
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
from typing import Iterable, Sequence

from aereo.backends.core import TaskRunner
from aereo.interfaces import ExecutionBackend, ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()


def _run_tasks_parallel(
    tasks: Sequence[ExtractionTask],
    runner: TaskRunner | None,
    max_workers: int | None,
    executor_cls: type[ProcessPoolExecutor] | type[ThreadPoolExecutor],
    *,
    backend_name: str,
    failure_log_key: str,
) -> Iterable[GeoDataFrame[ArtifactSchema]]:
    """Run tasks sequentially or via the supplied executor class.

    Args:
        tasks: Extraction tasks to run.
        runner: TaskRunner that resolves and executes each task.
        max_workers: Maximum workers for the executor. ``None`` runs sequentially.
        executor_cls: Either :class:`ProcessPoolExecutor` or
            :class:`ThreadPoolExecutor`.
        backend_name: Human-readable backend name for error messages.
        failure_log_key: Structured-log key used when a task fails.

    Returns:
        An iterable of ``GeoDataFrame[ArtifactSchema]`` results, one per task,
        in the same order as *tasks*.

    Raises:
        ValueError: If *runner* is ``None``.
    """
    if runner is None:
        raise ValueError(f"{backend_name} requires a runner")
    if not tasks:
        return []

    if max_workers is None or len(tasks) == 1:
        return [runner.run(t) for t in tasks]

    results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * len(tasks)
    with executor_cls(max_workers=max_workers) as executor:
        futures = {executor.submit(runner.run, task): i for i, task in enumerate(tasks)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                logger.error(
                    failure_log_key,
                    task_index=idx,
                    error=str(exc),
                )
                raise

    return [r for r in results if r is not None]


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
        runner: TaskRunner | None = None,
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
        return _run_tasks_parallel(
            tasks,
            runner,
            self.max_workers,
            ProcessPoolExecutor,
            backend_name="LocalProcessBackend",
            failure_log_key="local_task_failed",
        )


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
        runner: TaskRunner | None = None,
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
        return _run_tasks_parallel(
            tasks,
            runner,
            self.max_workers,
            ThreadPoolExecutor,
            backend_name="ThreadBackend",
            failure_log_key="thread_task_failed",
        )
