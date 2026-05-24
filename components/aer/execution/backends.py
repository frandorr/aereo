"""Remote execution backends for AER extraction tasks."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

from aer.execution.core import TaskRunner, TaskStaging
from aer.interfaces import ExtractionTask
from aer.schemas import ArtifactSchema
from aer.serialization import TaskSerializer
from pandera.typing.geopandas import GeoDataFrame

logger = logging.getLogger(__name__)


class LambdaBackend:
    """Execute tasks remotely via AWS Lambda container functions.

    Each :class:`ExtractionTask` is serialized, staged to remote object storage,
    and dispatched as a separate Lambda invocation.  The Lambda handler is
    expected to deserialize the task, run the appropriate extractor, upload the
    results, and return a JSON payload with a ``manifest_uri`` key.

    Because ``boto3`` is an optional dependency, it is imported lazily inside
    :meth:`__init__`.  Install it with ``pip install boto3`` before using this
    backend.
    """

    def __init__(
        self,
        function_name: str,
        staging: TaskStaging,
        serializer: TaskSerializer | None = None,
        endpoint_url: str | None = None,
    ):
        """Create a new Lambda backend.

        Args:
            function_name: AWS Lambda function name or ARN.
            staging: A :class:`TaskStaging` implementation that knows how to upload
                serialized tasks and download result manifests.
            serializer: Optional :class:`TaskSerializer` instance.  A default one
                is created when ``None``.
            endpoint_url: Optional boto3 endpoint URL (e.g. ``http://localhost:4566``
                for Floci/local emulation).
        """
        try:
            import boto3  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for LambdaBackend. "
                "Install it with: pip install boto3"
            ) from exc

        self.function_name = function_name
        self.staging = staging
        self.serializer = serializer or TaskSerializer()
        self.lambda_client = boto3.client("lambda", endpoint_url=endpoint_url)

    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: TaskRunner,
    ) -> Iterable[GeoDataFrame[ArtifactSchema]]:
        """Execute *tasks* via AWS Lambda.

        The supplied *runner* is ignored because the remote Lambda container
        has its own :class:`TaskRunner` and plugin registry.

        Args:
            tasks: Extraction tasks to dispatch.
            runner: Client-side runner (ignored by this backend).

        Returns:
            An iterable of ``GeoDataFrame[ArtifactSchema]`` results, one per task.
        """
        # runner is ignored — Lambda handler has its own TaskRunner + registry
        results: list[GeoDataFrame[ArtifactSchema]] = []
        for task in tasks:
            job_id = task.task_context.get("job_id", "default")
            task_idx = task.task_context.get("chunk_id", 0)

            # 1. Stage serialized task
            with tempfile.TemporaryDirectory() as tmpdir:
                self.serializer.serialize(task, Path(tmpdir))
                task_uri = self.staging.stage(Path(tmpdir), job_id, task_idx)

            # 2. Invoke Lambda
            output_prefix = f"s3://{self.staging.bucket}/results/{job_id}/{task_idx}/"
            payload_dict = {
                "task_uri": task_uri,
                "output_prefix": output_prefix,
            }
            response = self.lambda_client.invoke(
                FunctionName=self.function_name,
                Payload=json.dumps(payload_dict).encode("utf-8"),
            )

            # 3. Inspect response
            payload_stream = response["Payload"]
            payload_bytes = payload_stream.read()

            if response.get("FunctionError"):
                error_msg = payload_bytes.decode("utf-8", errors="replace")
                logger.error(
                    "lambda_invocation_failed",
                    extra={
                        "function_name": self.function_name,
                        "job_id": job_id,
                        "task_idx": task_idx,
                        "error": error_msg,
                    },
                )
                raise RuntimeError(
                    f"Lambda function '{self.function_name}' returned error "
                    f"for task {task_idx} of job {job_id}: {error_msg}"
                )

            payload = json.loads(payload_bytes)
            manifest_uri = payload.get("manifest_uri")
            if manifest_uri is None:
                raise ValueError(
                    f"Lambda response missing 'manifest_uri' for task {task_idx} "
                    f"of job {job_id}: {payload}"
                )

            artifacts = self.staging.load_artifacts(manifest_uri)
            results.append(artifacts)

        return results
