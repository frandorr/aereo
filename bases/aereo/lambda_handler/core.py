"""AEREO Lambda handler entrypoint."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from aereo.backends import CloudTaskStaging, TaskRunner
from aereo.backends.lambda_backend import _safe_truncate
from aereo.registry import AereoRegistry
from aereo.serialization import TaskSerializer

logger = logging.getLogger(__name__)

# Initialize once per cold start
_registry = AereoRegistry()
_runner = TaskRunner(registry=_registry)
_serializer = TaskSerializer()


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    parts = uri[5:].split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key


def _download_prefix(s3: Any, bucket: str, prefix: str, dest_dir: Path) -> None:
    """Download all objects under *prefix* into *dest_dir*, preserving structure."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len(prefix) :].lstrip("/")
            if not rel:
                continue
            local_file = dest_dir / rel
            local_file.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(local_file))


def _is_retryable(exc: Exception) -> bool:
    """Return True if *exc* is a retryable error."""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    # botocore is imported lazily; handle gracefully when missing
    try:
        from botocore.exceptions import ClientError

        if isinstance(exc, ClientError):
            return True
    except Exception:
        pass
    return False


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AEREO Lambda handler entrypoint.

    Deserializes the task from S3, runs the execution backend,
    and uploads the results back to S3.
    """
    task_uri = event.get("task_uri", "")
    output_prefix = event.get("output_prefix", "")
    job_id = event.get("job_id", "unknown")
    chunk_id = event.get("chunk_id", -1)

    logger.info(
        "lambda_handler_start",
        extra={"job_id": job_id, "chunk_id": chunk_id, "task_uri": task_uri},
    )

    if not task_uri or not output_prefix:
        return {
            "statusCode": 400,
            "error": "Missing required fields: task_uri, output_prefix",
            "error_type": "ValueError",
            "retryable": False,
            "manifest_uri": None,
            "job_id": job_id,
            "chunk_id": chunk_id,
        }

    try:
        endpoint_url = os.environ.get("AWS_ENDPOINT_URL")

        # S3 bucket name is read from the event payload if present, otherwise parsed from task_uri
        bucket = event.get("bucket")
        if not bucket:
            bucket, prefix = _parse_s3_uri(task_uri)
        else:
            _, prefix = _parse_s3_uri(task_uri)

        import boto3  # pyright: ignore[reportMissingImports]

        s3 = boto3.client("s3", endpoint_url=endpoint_url)

        # Rebuild runner with any init_params passed in the event
        init_params = event.get("init_params")
        if init_params:
            runner = TaskRunner(registry=_registry, init_params=init_params)
        else:
            runner = _runner

        # 1. Download staged task
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _download_prefix(s3, bucket, prefix, task_dir)
            task = _serializer.deserialize(task_dir)

            # 2. Execute using the local plugin registry
            artifacts = runner.run(task)

            # 3. Upload results using CloudTaskStaging
            staging = CloudTaskStaging(bucket=bucket, endpoint_url=endpoint_url)
            upload_result = staging.upload_artifacts(artifacts, output_prefix)
            manifest_uri = upload_result["manifest_uri"]

        return {
            "statusCode": 200,
            "manifest_uri": manifest_uri,
            "job_id": job_id,
            "chunk_id": chunk_id,
        }

    except MemoryError:
        # Re-raise memory errors so the Lambda runtime can handle them
        raise

    except Exception as exc:
        error_msg = _safe_truncate(str(exc))
        logger.error(
            "lambda_handler_error",
            extra={
                "job_id": job_id,
                "chunk_id": chunk_id,
                "error_type": type(exc).__name__,
                "error": error_msg,
            },
            exc_info=True,
        )

        return {
            "statusCode": 500,
            "error": error_msg,
            "error_type": type(exc).__name__,
            "retryable": _is_retryable(exc),
            "manifest_uri": None,
            "job_id": job_id,
            "chunk_id": chunk_id,
        }
