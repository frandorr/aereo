"""AEREO Lambda handler entrypoint.

The handler receives a serialized :class:`~aereo.interfaces.ExtractionTask`
from S3, executes it through :func:`~aereo.execution.run_task`, and uploads
the resulting artifacts (GeoTIFFs + metadata) back to S3.

No plugin registry is required at module load time: the task itself carries
fully instantiated reader and writer callables on its parent
:class:`~aereo.pipeline.ExtractionJob` so the runner can execute it directly.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from aereo.execution import run_task
from aereo.executors._serialization import _TaskSerializer
from aereo.executors._staging import _CloudTaskStaging
from aereo.executors._lambda import _safe_truncate

logger = logging.getLogger(__name__)

_S3_PREFIX = "s3://"

# Initialize once per cold start.
_serializer = _TaskSerializer()


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse an S3 URI into bucket and key components.

    Args:
        uri: S3 URI (e.g., "s3://bucket/prefix/key").

    Returns:
        Tuple of (bucket, key).

    Raises:
        ValueError: If the URI is not a valid S3 URI.
    """
    if not uri.startswith(_S3_PREFIX):
        raise ValueError(f"Invalid S3 URI: {uri}")
    parts = uri[len(_S3_PREFIX) :].split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key


def _download_prefix(s3: Any, bucket: str, prefix: str, dest_dir: Path) -> None:
    """Download all objects under *prefix* into *dest_dir*, preserving structure.

    Args:
        s3: Boto3 S3 client.
        bucket: S3 bucket name.
        prefix: S3 key prefix to download from.
        dest_dir: Local directory to download files into.
    """
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
    """Return True if *exc* is a retryable error.

    Args:
        exc: The exception to check.

    Returns:
        True if the exception is retryable, False otherwise.
    """
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    # botocore is imported lazily; handle gracefully when missing
    try:
        from botocore.exceptions import ClientError  # type: ignore[reportMissingImports]

        if isinstance(exc, ClientError):
            return True
    except (ModuleNotFoundError, ImportError):
        pass
    return False


def _build_error_response(
    job_id: str,
    chunk_id: int,
    exc: Exception,
    status_code: int = 500,
    *,
    log_error: bool = True,
) -> dict[str, Any]:
    """Build a standardized error response dict.

    Args:
        job_id: Job identifier.
        chunk_id: Chunk identifier.
        exc: The exception that occurred.
        status_code: HTTP status code for the response.
        log_error: Whether to emit a logger error record.

    Returns:
        Error response dictionary.
    """
    error_msg = _safe_truncate(str(exc))
    if log_error:
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
        "statusCode": status_code,
        "error": error_msg,
        "error_type": type(exc).__name__,
        "retryable": _is_retryable(exc) if status_code == 500 else False,
        "manifest_uri": None,
        "job_id": job_id,
        "chunk_id": chunk_id,
    }


def _upload_artifacts_to_s3(
    s3: Any,
    artifacts: Any,
    output_prefix: str,
    timings: dict[str, Any],
    endpoint_url: str | None = None,
) -> str:
    """Upload GeoTIFF artifacts to S3 and update their URIs.

    Args:
        s3: Boto3 S3 client.
        artifacts: DataFrame containing artifact metadata.  Mutated in-place
            so that local file paths are replaced with S3 URIs.
        output_prefix: S3 prefix for output files.
        timings: Mutable timing dictionary to update.
        endpoint_url: Optional S3 endpoint URL (e.g. for LocalStack).

    Returns:
        The manifest URI from _CloudTaskStaging.
    """
    t4 = time.time()
    out_bucket, out_prefix = _parse_s3_uri(output_prefix)
    geotiff_count = 0
    for idx, row in artifacts.iterrows():
        local_path = Path(str(row["uri"]))
        if local_path.exists():
            rel_key = f"{out_prefix}{local_path.name}"
            s3.upload_file(str(local_path), out_bucket, rel_key)
            artifacts.at[idx, "uri"] = f"{_S3_PREFIX}{out_bucket}/{rel_key}"
            geotiff_count += 1
    timings["upload_geotiffs"] = time.time() - t4
    timings["geotiff_count"] = geotiff_count

    t5 = time.time()
    staging = _CloudTaskStaging(bucket=out_bucket, endpoint_url=endpoint_url)
    upload_result = staging.upload_artifacts(artifacts, output_prefix)
    timings["upload_metadata"] = time.time() - t5

    return upload_result["manifest_uri"]


def _format_timings(timings: dict[str, Any]) -> dict[str, Any]:
    """Convert raw timing floats to milliseconds with two-decimal rounding.

    Args:
        timings: Dictionary of timing names to float or other values.

    Returns:
        Dictionary with float values rounded to milliseconds.
    """
    return {
        k: round(v * 1000, 2) if isinstance(v, float) else v for k, v in timings.items()
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AEREO Lambda handler entrypoint.

    Deserializes the task from S3, runs the execution backend,
    and uploads the results back to S3.

    Args:
        event: Lambda event dictionary containing task_uri, output_prefix,
            job_id, chunk_id, and optional bucket and init_params.
        context: Lambda runtime context.

    Returns:
        Response dictionary with statusCode, manifest_uri or error details,
        job_id, chunk_id, and timings_ms.
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
        return _build_error_response(
            job_id,
            chunk_id,
            ValueError("Missing required fields: task_uri, output_prefix"),
            status_code=400,
            log_error=False,
        )

    try:
        endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
        bucket = event.get("bucket")
        if not bucket:
            bucket, prefix = _parse_s3_uri(task_uri)
        else:
            _, prefix = _parse_s3_uri(task_uri)

        import boto3  # pyright: ignore[reportMissingImports]

        s3 = boto3.client("s3", endpoint_url=endpoint_url)

        timings: dict[str, Any] = {}
        t0 = time.time()

        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)

            t1 = time.time()
            _download_prefix(s3, bucket, prefix, task_dir)
            timings["download_task"] = time.time() - t1

            t2 = time.time()
            task = _serializer.deserialize(task_dir)
            timings["deserialize_task"] = time.time() - t2

            t3 = time.time()
            artifacts = run_task(task)
            timings["extractor_run"] = time.time() - t3

            manifest_uri = _upload_artifacts_to_s3(
                s3, artifacts, output_prefix, timings, endpoint_url=endpoint_url
            )

        timings["total"] = time.time() - t0
        timings_ms = _format_timings(timings)
        logger.info(
            "lambda_handler_complete",
            extra={
                "job_id": job_id,
                "chunk_id": chunk_id,
                "timings_ms": timings_ms,
            },
        )

        return {
            "statusCode": 200,
            "manifest_uri": manifest_uri,
            "job_id": job_id,
            "chunk_id": chunk_id,
            "timings_ms": timings_ms,
        }

    except MemoryError:
        raise

    except Exception as exc:
        return _build_error_response(job_id, chunk_id, exc)
