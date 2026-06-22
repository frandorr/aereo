"""Remote execution backend for AWS Lambda."""

from __future__ import annotations

import json
import re
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Sequence

from aereo.backends.core import TaskRunner
from aereo.interfaces import ExecutionBackend, ExtractionTask, TaskStaging
from aereo.schemas import ArtifactSchema
from aereo.serialization import TaskSerializer
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()

# Regexes for redacting sensitive strings from Lambda error messages.
_RE_PRESIGNED_URL = re.compile(r"https?://[^\s]+\?[^\s]*X-Amz-Credential[^\s]*")
"""Matches presigned S3 URLs so they can be redacted from logs."""
_RE_AWS_KEY = re.compile(r"AKIA[0-9A-Z]{16}")
"""Matches AWS access key IDs so they can be redacted from logs."""


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


class RetryableLambdaError(RuntimeError):
    """Raised when a Lambda invocation fails with a retryable error."""


class LambdaBackend(ExecutionBackend):
    """Execute tasks remotely via AWS Lambda container functions.

    Each :class:`ExtractionTask` is serialized, staged to remote object storage,
    and dispatched as a separate Lambda invocation. The Lambda handler is
    expected to deserialize the task, run the appropriate extractor, upload the
    results, and return a JSON payload with a ``manifest_uri`` key.

    Because ``boto3`` is an optional dependency, it is imported lazily inside
    :meth:`__init__`. Install it with ``pip install boto3`` before using this
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
        lambda_url: str | None = None,
    ) -> None:
        """Create a new Lambda backend.

        Args:
            function_name: AWS Lambda function name or ARN.
            staging: A :class:`TaskStaging` implementation that knows how to upload
                serialized tasks and download result manifests.
            serializer: Optional :class:`TaskSerializer` instance. A default one
                is created when ``None``.
            endpoint_url: Optional boto3 endpoint URL (e.g. ``http://localhost:4566``
                for LocalStack emulation).
            max_concurrent_invokes: Maximum number of concurrent Lambda invocations.
            invoke_timeout: Read timeout in seconds for the boto3 Lambda client.
            lambda_url: Optional direct HTTP URL for the Lambda function. When set,
                the backend POSTs the invocation payload to this URL instead of using
                ``boto3``. This is useful for testing against the Lambda Runtime
                Interface Emulator (RIE).

        Raises:
            ImportError: If ``boto3`` is not installed and ``lambda_url`` is ``None``.
        """
        self.function_name = function_name
        self.staging = staging
        self.serializer = serializer or TaskSerializer()
        self.max_concurrent_invokes = max_concurrent_invokes
        self._lambda_url = lambda_url
        self._invoke_timeout = invoke_timeout

        if lambda_url is None:
            try:
                import boto3  # pyright: ignore[reportMissingImports]
                from botocore.config import Config  # pyright: ignore[reportMissingImports]
            except ImportError as exc:
                raise ImportError(
                    "boto3 is required for LambdaBackend. "
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
        else:
            self._lambda_client = None

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

        Raises:
            RuntimeError: If a Lambda invocation fails or returns a non-2xx
                status code.
            RetryableLambdaError: If the Lambda returns a retryable error.
            ValueError: If the response is missing ``manifest_uri``.
        """
        if not tasks:
            return []

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
                    logger.error(
                        "lambda_task_failed",
                        task_index=idx,
                        error=str(exc),
                    )
                    raise

        return [results_map[i] for i in range(len(tasks))]

    def _invoke_single(self, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
        """Serialize, stage, invoke Lambda, and load artifacts for one task.

        Args:
            task: The extraction task to process.

        Returns:
            The extracted artifacts as a ``GeoDataFrame[ArtifactSchema]``.

        Raises:
            RuntimeError: If the Lambda invocation fails or returns a non-2xx
                status code.
            RetryableLambdaError: If the Lambda returns a retryable error.
            ValueError: If the response is missing ``manifest_uri``.
        """
        job_id = task.task_context.get("job_id", "default")
        task_idx = task.task_context.get("chunk_id", 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            self.serializer.serialize(task, Path(tmpdir))
            task_uri = self.staging.stage(Path(tmpdir), job_id, task_idx)

        output_prefix = self.staging.result_prefix(job_id, task_idx)
        payload_dict = {
            "task_uri": task_uri,
            "output_prefix": output_prefix,
            "job_id": job_id,
            "chunk_id": task_idx,
            "init_params": task.task_context.get("init_params"),
            "bucket": self.staging.bucket,
        }
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

        return self.staging.load_artifacts(manifest_uri)

    def _invoke_payload(
        self, payload_dict: dict[str, Any], job_id: str, task_idx: int
    ) -> bytes:
        """Dispatch *payload_dict* and return the raw response body."""
        payload_json = json.dumps(payload_dict, default=str).encode("utf-8")

        if self._lambda_url is not None:
            return self._invoke_via_http(payload_json)

        assert self._lambda_client is not None
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

    def _invoke_via_http(self, payload_json: bytes) -> bytes:
        """POST *payload_json* directly to :attr:`_lambda_url`.

        Raises:
            RuntimeError: If the HTTP request fails or returns a non-2xx code.
        """
        request = urllib.request.Request(
            self._lambda_url,  # type: ignore[arg-type]
            data=payload_json,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._invoke_timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Lambda HTTP invocation failed ({exc.code}): {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Lambda HTTP invocation failed: {exc.reason}") from exc
