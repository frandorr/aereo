"""Core client implementation for the Aereo geospatial pipeline.

This module defines :class:`AereoClient` and its supporting utilities.
"""

from collections.abc import Sequence
from enum import Enum
from typing import cast

import pandas as pd
from aereo.backends import LocalProcessBackend, TaskRunner
from aereo.cache import TaskResultCache
from aereo.interfaces import ExecutionBackend, ExtractionTask, SearchProvider
from aereo.pipeline import ExtractionJob
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()


class FailureMode(str, Enum):
    """Determines pipeline behavior when partial or total plugin failures occur."""

    STRICT = "strict"
    BEST_EFFORT = "best_effort"


class AereoClient:
    """Core external entrypoint orchestrating the Geospatial pipeline.

    Responsibilities:
    - Execute search dispatch to remote plugin APIs.
    - Build extraction tasks from search results via the job's task builder.
    - Execute prepared tasks through a configurable backend.
    """

    def __init__(self, backend: ExecutionBackend | None = None):
        """Initialize the AereoClient.

        Args:
            backend: Default execution backend for :meth:`execute_tasks`.
        """
        self._backend = backend

    def search(self, search_provider: SearchProvider) -> GeoDataFrame[AssetSchema]:
        """Execute search via the given search provider.

        Args:
            search_provider: SearchProvider instance to execute.

        Returns:
            A verified GeoDataFrame of combined search results.
        """
        logger.info("search_called", provider=search_provider.__class__.__name__)
        return search_provider()

    def build_tasks(
        self,
        search_results: GeoDataFrame[AssetSchema],
        job: ExtractionJob,
    ) -> Sequence[ExtractionTask]:
        """Build extraction tasks from search results using the job's task builder.

        Args:
            search_results: The merged GeoDataFrame of search results to prepare.
            job: Parent ``ExtractionJob`` whose ``task_builder`` produces tasks.

        Returns:
            A sequence of prepared ``ExtractionTask`` objects.
        """
        if search_results.empty:
            return []

        logger.info(
            "build_tasks_start",
            builder=job.task_builder.__class__.__name__,
            assets=len(search_results),
        )
        return job.task_builder(search_results, job)

    def execute_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        backend: ExecutionBackend | None = None,
        failure_mode: FailureMode = FailureMode.STRICT,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Execute a sequence of ExtractionTasks through a configurable backend.

        Args:
            tasks: A sequence of ExtractionTasks, usually from :meth:`build_tasks`.
            backend: An ExecutionBackend implementation. Defaults to LocalProcessBackend().
            failure_mode: STRICT raises on the first failure; BEST_EFFORT processes tasks individually.

        Returns:
            A unified GeoDataFrame containing all extracted Artifacts.
        """
        if not tasks:
            logger.warning("execute_tasks_empty", reason="No tasks provided")
            return cast(GeoDataFrame, ArtifactSchema.empty())

        backend = backend or self._backend or LocalProcessBackend()
        cache = TaskResultCache()
        runner = TaskRunner(
            per_cell_failure_mode="strict"
            if failure_mode == FailureMode.STRICT
            else "best_effort",
            cache=cache,
        )

        logger.info(
            "execute_tasks_start",
            task_count=len(tasks),
            backend=backend.__class__.__name__,
            failure_mode=failure_mode.value,
        )

        if failure_mode == FailureMode.BEST_EFFORT:
            results: list[GeoDataFrame[ArtifactSchema]] = []
            for task in tasks:
                try:
                    task_results = list(backend.run_tasks([task], runner))
                    if task_results:
                        results.append(task_results[0])
                except Exception:
                    logger.warning("task_failed_best_effort", exc_info=True)
            if not results:
                logger.warning("execute_tasks_empty_result")
                return cast(GeoDataFrame, ArtifactSchema.empty())

            concatenated = pd.concat(results, ignore_index=True)
            return cast(GeoDataFrame, ArtifactSchema.validate(concatenated))

        # STRICT mode — batch for efficiency, raise on first failure
        try:
            results = list(backend.run_tasks(tasks, runner))
        except Exception:
            logger.error("execute_tasks_failed", exc_info=True)
            raise

        if not results:
            return cast(GeoDataFrame, ArtifactSchema.empty())

        concatenated = pd.concat(results, ignore_index=True)
        return cast(GeoDataFrame, ArtifactSchema.validate(concatenated))
