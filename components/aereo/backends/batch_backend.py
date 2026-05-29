"""Remote execution backend for AWS Batch."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from aereo.backends.core import TaskRunner
from aereo.interfaces import ExecutionBackend, ExtractionTask, TaskStaging
from aereo.schemas import ArtifactSchema
from aereo.serialization import TaskSerializer
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()

# Default polling interval and timeout
_DEFAULT_POLL_INTERVAL = 30  # seconds
_DEFAULT_MAX_WAIT = 7200  # 2 hours


class BatchBackend(ExecutionBackend):
    """Execute tasks remotely via AWS Batch on EC2 Spot instances.

    Each :class:`ExtractionTask` is serialized, staged to S3, and dispatched
    as an AWS Batch array job. The Batch container reads the task from S3,
    executes the extractor, uploads results back to S3, and exits.

    Because ``boto3`` is an optional dependency, it is imported lazily inside
    :meth:`__init__`. Install it with ``pip install boto3`` before using this
    backend.

    Attributes:
        job_queue: Name of the AWS Batch job queue.
        job_definition: Name of the AWS Batch job definition.
        staging: A :class:`TaskStaging` implementation for S3 upload/download.
        region: AWS region.
        serializer: TaskSerializer instance.
        poll_interval: Seconds between job status polls.
        max_wait_seconds: Maximum seconds to wait for job completion.
        array_size: Maximum array size for a single Batch array job.
            AWS Batch limits array jobs to 10,000 child jobs.
    """

    def __init__(
        self,
        job_queue: str,
        job_definition: str,
        staging: TaskStaging,
        region: str = "us-west-2",
        serializer: TaskSerializer | None = None,
        poll_interval: int = _DEFAULT_POLL_INTERVAL,
        max_wait_seconds: int = _DEFAULT_MAX_WAIT,
        array_size: int = 10_000,
    ) -> None:
        """Create a new Batch backend.

        Args:
            job_queue: AWS Batch job queue name.
            job_definition: AWS Batch job definition name.
            staging: A :class:`TaskStaging` implementation.
            region: AWS region.
            serializer: Optional :class:`TaskSerializer`.
            poll_interval: Seconds between DescribeJobs API polls.
            max_wait_seconds: Maximum total wait time before giving up.
            array_size: Maximum number of tasks per array job.

        Raises:
            ImportError: If ``boto3`` is not installed.
        """
        try:
            import boto3  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for BatchBackend. "
                "Install it with: pip install boto3"
            ) from exc

        self.job_queue = job_queue
        self.job_definition = job_definition
        self.staging = staging
        self.region = region
        self.serializer = serializer or TaskSerializer()
        self.poll_interval = poll_interval
        self.max_wait_seconds = max_wait_seconds
        self.array_size = array_size
        self._batch_client = boto3.client("batch", region_name=region)

    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: Optional[TaskRunner] = None,
    ) -> Iterable[GeoDataFrame[ArtifactSchema]]:
        """Execute *tasks* via AWS Batch.

        The supplied *runner* is ignored because the remote Batch container
        has its own :class:`TaskRunner` and plugin registry.

        Tasks are grouped into array jobs for efficiency. Each array job
        handles up to *array_size* tasks.

        Args:
            tasks: Extraction tasks to dispatch.
            runner: Client-side runner (ignored by this backend).

        Returns:
            An iterable of ``GeoDataFrame[ArtifactSchema]`` results, one per task.
        """
        if not tasks:
            return []

        # Stage all tasks first and collect URIs
        job_id = tasks[0].task_context.get("job_id", "default")
        staged_tasks = self._stage_tasks(tasks, job_id)

        # Group into array job batches
        results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * len(tasks)
        total_batches = (len(tasks) + self.array_size - 1) // self.array_size

        for batch_idx in range(total_batches):
            start = batch_idx * self.array_size
            end = min(start + self.array_size, len(tasks))
            batch_tasks = staged_tasks[start:end]
            batch_size = len(batch_tasks)

            logger.info(
                "batch_submit",
                batch_idx=batch_idx,
                total_batches=total_batches,
                batch_size=batch_size,
                job_queue=self.job_queue,
            )

            # Submit array job
            job_name = f"aereo-{job_id}-{batch_idx}"
            array_job_id = self._submit_array_job(
                job_name=job_name,
                array_size=batch_size,
                staged_tasks=batch_tasks,
            )

            # Wait for completion and collect results
            batch_results = self._wait_and_collect(
                array_job_id=array_job_id,
                batch_size=batch_size,
                staged_tasks=batch_tasks,
            )

            # Map batch results back to original task indices
            for i, result in enumerate(batch_results):
                results[start + i] = result

        return [r for r in results if r is not None]

    def _stage_tasks(
        self, tasks: Sequence[ExtractionTask], job_id: str
    ) -> list[dict[str, Any]]:
        """Serialize and stage all tasks to S3.

        Returns:
            List of dicts with keys: task_uri, output_prefix, chunk_id, task.
        """
        staged = []
        for task_idx, task in enumerate(tasks):
            with tempfile.TemporaryDirectory() as tmpdir:
                self.serializer.serialize(task, Path(tmpdir))
                task_uri = self.staging.stage(Path(tmpdir), job_id, task_idx)

            output_prefix = self.staging.result_prefix(job_id, task_idx)
            staged.append({
                "task_uri": task_uri,
                "output_prefix": output_prefix,
                "chunk_id": task_idx,
                "task": task,
            })

            logger.debug(
                "task_staged",
                task_idx=task_idx,
                task_uri=task_uri,
            )

        return staged

    def _submit_array_job(
        self,
        job_name: str,
        array_size: int,
        staged_tasks: list[dict[str, Any]],
    ) -> str:
        """Submit an AWS Batch array job.

        Args:
            job_name: Name for the job.
            array_size: Number of child array elements.
            staged_tasks: List of staged task metadata dicts.

        Returns:
            The AWS Batch job ID.
        """
        # Build environment variables for the container
        # The batch handler reads TASK_URI, OUTPUT_PREFIX, etc. from env
        # For array jobs, we use the array index to look up the correct task
        # We pass all task URIs as a JSON list in env var
        task_uris = [t["task_uri"] for t in staged_tasks]
        output_prefixes = [t["output_prefix"] for t in staged_tasks]
        chunk_ids = [str(t["chunk_id"]) for t in staged_tasks]

        container_overrides = {
            "environment": [
                {"name": "AEREO_BATCH_MODE", "value": "array"},
                {"name": "AEREO_TASK_URIS", "value": json.dumps(task_uris)},
                {"name": "AEREO_OUTPUT_PREFIXES", "value": json.dumps(output_prefixes)},
                {"name": "AEREO_CHUNK_IDS", "value": json.dumps(chunk_ids)},
                {"name": "AEREO_JOB_ID", "value": job_name},
                {
                    "name": "BUCKET",
                    "value": getattr(self.staging, "bucket", ""),
                },
            ]
        }

        # Add init_params if present in first task
        first_task = staged_tasks[0]["task"]
        init_params = first_task.task_context.get("init_params")
        if init_params:
            container_overrides["environment"].append({
                "name": "INIT_PARAMS",
                "value": json.dumps(init_params),
            })

        response = self._batch_client.submit_job(
            jobName=job_name,
            jobQueue=self.job_queue,
            jobDefinition=self.job_definition,
            arrayProperties={"size": array_size},
            containerOverrides=container_overrides,
            retryStrategy={
                "attempts": 2,
                "evaluateOnExit": [
                    {
                        "onStatusReason": "Host EC2*",
                        "action": "RETRY",
                    },
                    {
                        "onReason": "*",
                        "action": "EXIT",
                    },
                ],
            },
        )

        job_id = response["jobId"]
        logger.info(
            "batch_job_submitted",
            job_name=job_name,
            job_id=job_id,
            array_size=array_size,
        )
        return job_id

    def _wait_and_collect(
        self,
        array_job_id: str,
        batch_size: int,
        staged_tasks: list[dict[str, Any]],
    ) -> list[GeoDataFrame[ArtifactSchema] | None]:
        """Poll job status until complete, then load artifacts.

        Args:
            array_job_id: The AWS Batch array job ID.
            batch_size: Number of array elements.
            staged_tasks: List of staged task metadata.

        Returns:
            List of results (GeoDataFrames), None for failed tasks.
        """
        # Build list of child job IDs
        child_job_ids = [f"{array_job_id}:{i}" for i in range(batch_size)]
        results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * batch_size

        start_time = time.time()
        pending = set(child_job_ids)

        while pending and (time.time() - start_time) < self.max_wait_seconds:
            # Poll status for pending jobs
            response = self._batch_client.describe_jobs(jobs=list(pending))

            for job in response["jobs"]:
                job_id = job["jobId"]
                status = job["status"]

                if status in ("SUCCEEDED", "FAILED"):
                    pending.discard(job_id)
                    array_index = int(job_id.split(":")[-1])

                    if status == "SUCCEEDED":
                        # Load artifacts from S3
                        try:
                            output_prefix = staged_tasks[array_index]["output_prefix"]
                            manifest_uri = f"{output_prefix}manifest.json"
                            results[array_index] = self.staging.load_artifacts(
                                manifest_uri
                            )
                            logger.info(
                                "batch_task_completed",
                                array_index=array_index,
                                job_id=job_id,
                            )
                        except Exception as exc:
                            logger.error(
                                "batch_load_artifacts_failed",
                                array_index=array_index,
                                job_id=job_id,
                                error=str(exc),
                            )
                    else:
                        # Log failure reason
                        reason = job.get("statusReason", "Unknown")
                        logger.error(
                            "batch_task_failed",
                            array_index=array_index,
                            job_id=job_id,
                            reason=reason,
                        )

            if pending:
                time.sleep(self.poll_interval)

        if pending:
            logger.warning(
                "batch_timeout",
                pending_count=len(pending),
                array_job_id=array_job_id,
            )

        return results
