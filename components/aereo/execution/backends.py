"""Remote execution backends for AER extraction tasks."""

from __future__ import annotations

import json
import logging
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Sequence

from aereo.execution.core import TaskRunner, TaskStaging
from aereo.interfaces import ExtractionTask
from aereo.schemas import ArtifactSchema
from aereo.serialization import TaskSerializer
from pandera.typing.geopandas import GeoDataFrame

logger = logging.getLogger(__name__)


def _safe_truncate(text: str, max_len: int = 2048) -> str:
    """Truncate error text and redact potential credentials."""
    text = re.sub(
        r"https?://[^\s]+\?[^\s]*X-Amz-Credential[^\s]*",
        "[REDACTED-PRESIGNED-URL]",
        text,
    )
    text = re.sub(r"AKIA[0-9A-Z]{16}", "[REDACTED-AWS-KEY]", text)
    if len(text) > max_len:
        text = text[:max_len] + f"... [{len(text) - max_len} chars truncated]"
    return text


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
        max_concurrent_invokes: int = 10,
        invoke_timeout: int = 900,
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
            max_concurrent_invokes: Maximum number of concurrent Lambda invocations.
            invoke_timeout: Read timeout in seconds for the boto3 Lambda client.
        """
        try:
            import boto3  # pyright: ignore[reportMissingImports]
            from botocore.config import Config  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for LambdaBackend. "
                "Install it with: pip install boto3"
            ) from exc

        self.function_name = function_name
        self.staging = staging
        self.serializer = serializer or TaskSerializer()
        self.max_concurrent_invokes = max_concurrent_invokes
        self._lambda_client = boto3.client(
            "lambda",
            endpoint_url=endpoint_url,
            config=Config(
                read_timeout=invoke_timeout,
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        )

    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: TaskRunner | None = None,
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
        if not tasks:
            return []

        if len(tasks) == 1:
            return [self._invoke_single(tasks[0])]

        results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * len(tasks)
        with ThreadPoolExecutor(max_workers=self.max_concurrent_invokes) as executor:
            futures = {
                executor.submit(self._invoke_single, task): i
                for i, task in enumerate(tasks)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.error(
                        "lambda_task_failed",
                        extra={"task_index": idx, "error": str(exc)},
                    )
                    raise

        return [r for r in results if r is not None]

    def _invoke_single(self, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
        """Serialize, stage, invoke Lambda, and load artifacts for one task."""
        job_id = task.task_context.get("job_id", "default")
        task_idx = task.task_context.get("chunk_id", 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            self.serializer.serialize(task, Path(tmpdir))
            task_uri = self.staging.stage(Path(tmpdir), job_id, task_idx)

        output_prefix = self.staging.result_prefix(job_id, task_idx)
        payload_dict = {
            "task_uri": task_uri,
            "output_prefix": output_prefix,
        }
        response = self._lambda_client.invoke(
            FunctionName=self.function_name,
            Payload=json.dumps(payload_dict).encode("utf-8"),
        )

        payload_stream = response["Payload"]
        payload_bytes = payload_stream.read()

        if response.get("FunctionError"):
            error_msg = _safe_truncate(
                payload_bytes.decode("utf-8", errors="replace"), 2048
            )
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

        # Handle structured error responses from the Lambda handler
        status_code = payload.get("statusCode", 200)
        if status_code >= 400:
            error = payload.get("error", "Unknown Lambda error")
            if payload.get("retryable"):
                raise RetryableLambdaError(error)
            raise RuntimeError(f"Lambda returned error: {error}")

        manifest_uri = payload.get("manifest_uri")
        if manifest_uri is None:
            raise ValueError(
                f"Lambda response missing 'manifest_uri' for task {task_idx} "
                f"of job {job_id}: {payload}"
            )

        return self.staging.load_artifacts(manifest_uri)


class RetryableLambdaError(RuntimeError):
    """Raised when a Lambda invocation fails with a retryable error."""
