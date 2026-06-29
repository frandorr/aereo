"""Remote executor for AWS Lambda."""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Literal, cast

import geopandas as gpd
import pandas as pd
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

from aereo.executors._serialization import _TaskSerializer
from aereo.executors._staging import _CloudTaskStaging
from aereo.interfaces import ExtractionTask
from aereo.schemas import ArtifactSchema
from aereo.storage import StorageBackend, storage_for_uri

logger = get_logger()

_STRICT_MODE = "strict"
_BEST_EFFORT_MODE = "best_effort"


class RetryableLambdaError(RuntimeError):
    """Raised when a Lambda invocation fails with a retryable error."""


class LambdaExecutor:
    """Execute extraction tasks remotely via AWS Lambda.

    Each :class:`ExtractionTask` is serialized, staged to S3, and dispatched as
    a separate Lambda invocation. The Lambda handler is expected to deserialize
    the task, run the extraction, upload the results, and return a JSON payload
    with a ``manifest_uri`` key.

    Because ``boto3`` is an optional dependency, it is imported lazily inside
    :meth:`__init__`. Install it with ``pip install boto3`` before using this
    executor.
    """

    def __init__(
        self,
        function_name: str,
        staging_bucket: str,
        storage: StorageBackend | None = None,
        failure_mode: Literal["strict", "best_effort"] = _STRICT_MODE,
        endpoint_url: str | None = None,
        max_concurrent_invokes: int = 10,
        invoke_timeout: int = 900,
    ) -> None:
        """Create a new Lambda executor.

        Args:
            function_name: AWS Lambda function name or ARN.
            staging_bucket: S3 bucket used to stage serialized tasks.
            storage: Optional storage backend used to load result manifests.
                When ``None``, a backend is resolved from each manifest URI.
            failure_mode: ``"strict"`` aborts on the first failed task;
                ``"best_effort"`` skips failed tasks and returns successful ones.
            endpoint_url: Optional boto3 endpoint URL (e.g. ``http://localhost:4566``
                for LocalStack emulation).
            max_concurrent_invokes: Maximum number of concurrent Lambda invocations.
            invoke_timeout: Read timeout in seconds for the boto3 Lambda client.

        Raises:
            ImportError: If ``boto3`` is not installed.
        """
        self.function_name = function_name
        self.staging_bucket = staging_bucket
        self.storage = storage
        self.failure_mode = failure_mode
        self.endpoint_url = endpoint_url
        self.max_concurrent_invokes = max_concurrent_invokes
        self._invoke_timeout = invoke_timeout

        self._serializer = _TaskSerializer()
        self._staging = _CloudTaskStaging(
            bucket=staging_bucket, endpoint_url=endpoint_url
        )

        try:
            import boto3  # pyright: ignore[reportMissingImports]
            from botocore.config import Config  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for LambdaExecutor. "
                "Install it with: pip install boto3"
            ) from exc

        self._lambda_client = boto3.client(
            "lambda",
            endpoint_url=endpoint_url,
            config=Config(
                read_timeout=invoke_timeout,
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        )

    def __call__(self, tasks: Sequence[ExtractionTask]) -> GeoDataFrame[ArtifactSchema]:
        """Execute *tasks* via AWS Lambda and return a unified artifact GeoDataFrame.

        Args:
            tasks: Extraction tasks to dispatch.

        Returns:
            A validated ``GeoDataFrame[ArtifactSchema]``.

        Raises:
            RuntimeError: If a Lambda invocation fails or returns a non-2xx
                status code.
            RetryableLambdaError: If the Lambda returns a retryable error.
            ValueError: If the response is missing ``manifest_uri``.
        """
        if not tasks:
            return cast(
                GeoDataFrame[ArtifactSchema], ArtifactSchema.empty_geodataframe()
            )

        results_map: dict[int, GeoDataFrame[ArtifactSchema]] = {}
        with ThreadPoolExecutor(max_workers=self.max_concurrent_invokes) as executor:
            futures = {
                executor.submit(self._invoke_single, task): i
                for i, task in enumerate(tasks)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results_map[idx] = future.result()
                except Exception as exc:
                    if self.failure_mode == _STRICT_MODE:
                        for pending in futures:
                            pending.cancel()
                        raise
                    logger.warning(
                        "lambda_task_failed_best_effort",
                        task_index=idx,
                        error=str(exc),
                    )

        ordered = [results_map[i] for i in range(len(tasks)) if i in results_map]
        if not ordered:
            return cast(
                GeoDataFrame[ArtifactSchema], ArtifactSchema.empty_geodataframe()
            )

        return cast(
            GeoDataFrame[ArtifactSchema],
            gpd.GeoDataFrame(
                pd.concat(ordered, ignore_index=True), geometry="geometry"
            ),
        )

    def _invoke_single(self, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
        """Serialize, stage, invoke Lambda, and load artifacts for one task."""
        job_id = task.task_context.get("job_id", "default")
        task_idx = task.task_context.get("chunk_id", 0)

        payload_dict = self._prepare_payload(task, job_id, task_idx)
        payload_bytes = self._invoke_payload(payload_dict, job_id, task_idx)

        payload = json.loads(payload_bytes)

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

        return self._load_manifest(manifest_uri)

    def _prepare_payload(
        self, task: ExtractionTask, job_id: str, task_idx: int
    ) -> dict[str, Any]:
        """Build the staged invocation payload for *task*."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._serializer.serialize(task, Path(tmpdir))
            task_uri = self._staging.stage(Path(tmpdir), job_id, task_idx)

        output_prefix = self._staging.result_prefix(job_id, task_idx)
        return {
            "mode": "staged",
            "task_uri": task_uri,
            "output_prefix": output_prefix,
            "job_id": job_id,
            "chunk_id": task_idx,
            "init_params": task.task_context.get("init_params"),
            "bucket": self._staging.bucket,
        }

    def _load_manifest(self, manifest_uri: str) -> GeoDataFrame[ArtifactSchema]:
        """Load artifacts from a manifest URI using the configured or resolved storage."""
        storage = self.storage or storage_for_uri(manifest_uri)
        return storage.load_artifacts(manifest_uri)

    def _invoke_payload(
        self, payload_dict: dict[str, Any], job_id: str, task_idx: int
    ) -> bytes:
        """Dispatch *payload_dict* to Lambda and return the raw response body."""
        payload_json = json.dumps(payload_dict, default=str).encode("utf-8")

        response = self._lambda_client.invoke(
            FunctionName=self.function_name,
            Payload=payload_json,
        )

        payload_stream = response["Payload"]
        payload_bytes = payload_stream.read()

        if response.get("FunctionError"):
            error_msg = _safe_truncate(
                payload_bytes.decode("utf-8", errors="replace"), 2048
            )
            logger.error(
                "lambda_invocation_failed",
                function_name=self.function_name,
                job_id=job_id,
                task_idx=task_idx,
                error=error_msg,
            )
            raise RuntimeError(
                f"Lambda function '{self.function_name}' returned error "
                f"for task {task_idx} of job {job_id}: {error_msg}"
            )

        return payload_bytes


# Regexes for redacting sensitive strings from Lambda error messages.
_RE_PRESIGNED_URL = re.compile(r"https?://[^\s]+\?[^\s]*X-Amz-Credential[^\s]*")
_RE_AWS_KEY = re.compile(r"AKIA[0-9A-Z]{16}")


def _safe_truncate(text: str, max_len: int = 2048) -> str:
    """Truncate error text and redact potential credentials.

    Args:
        text: Raw error text that may contain sensitive URLs or keys.
        max_len: Maximum length before truncation.

    Returns:
        Sanitised text with credentials redacted and length capped.
    """
    text = _RE_PRESIGNED_URL.sub("[REDACTED-PRESIGNED-URL]", text)
    text = _RE_AWS_KEY.sub("[REDACTED-AWS-KEY]", text)
    if len(text) > max_len:
        text = text[:max_len] + f"... [{len(text) - max_len} chars truncated]"
    return text
