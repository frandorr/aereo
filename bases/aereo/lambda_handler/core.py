"""AEREO Lambda handler entrypoint."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from aereo.backends import CloudTaskStaging, TaskRunner
from aereo.backends.lambda_backend import _safe_truncate
from aereo.registry import AereoRegistry
from aereo.serialization import TaskSerializer

logger = logging.getLogger(__name__)

# Initialize once per cold start — eagerly import plugins to avoid
# the ~20-30s entry-point scanning overhead in Lambda.
_registry = AereoRegistry(auto_discover=False)

# Eagerly register known plugins (import once, fast path).
# Use conditional imports so the image stays lean — only plugins
# that were actually installed in the Dockerfile get registered.
_plugins_to_register: dict[str, Any] = {}

_extract_plugins = [
    ("extract_satpy", "aereo.extract_satpy.core", "SatpyExtractor"),
    ("extract_aws_goes", "aereo.extract_aws_goes.core", "AwsGoesExtractor"),
    ("extract_lazycogs", "aereo.extract_lazycogs.core", "ExtractLazycogs"),
    ("extract_odc_stac", "aereo.extract_odc_stac.core", "ExtractOdcStac"),
    ("extract_tessera", "aereo.extract_tessera.core", "ExtractTessera"),
]

_search_plugins = [
    ("search_aws_goes", "aereo.search_aws_goes.core", "AwsGoesSearcher"),
    ("search_earthaccess", "aereo.search_earthaccess.core", "EarthAccessSearcher"),
    (
        "search_planetary_computer",
        "aereo.search_planetary_computer.core",
        "PlanetaryComputerSearcher",
    ),
    ("search_rustac", "aereo.search_rustac.core", "RustacSearcher"),
    ("search_tessera", "aereo.search_tessera.core", "TesseraSearcher"),
]

for name, module, cls_name in _extract_plugins + _search_plugins:
    try:
        mod = __import__(module, fromlist=[cls_name])
        _plugins_to_register[name] = getattr(mod, cls_name)
    except Exception:
        pass  # Plugin not installed — skip

_registry.register_plugins(_plugins_to_register)

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

        # Timing instrumentation
        timings = {}
        t0 = time.time()

        # 1. Download staged task
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            t1 = time.time()
            _download_prefix(s3, bucket, prefix, task_dir)
            timings["download_task"] = time.time() - t1

            t2 = time.time()
            task = _serializer.deserialize(task_dir)
            timings["deserialize_task"] = time.time() - t2

            # 2. Execute using the local plugin registry
            t3 = time.time()
            artifacts = runner.run(task)
            timings["extractor_run"] = time.time() - t3

            # 3. Upload actual GeoTIFF files and update URIs
            t4 = time.time()
            out_bucket, out_prefix = _parse_s3_uri(output_prefix)
            geotiff_count = 0
            for idx, row in artifacts.iterrows():
                local_path = Path(str(row["uri"]))
                if local_path.exists():
                    rel_key = f"{out_prefix}{local_path.name}"
                    s3.upload_file(str(local_path), out_bucket, rel_key)
                    artifacts.at[idx, "uri"] = f"s3://{out_bucket}/{rel_key}"
                    geotiff_count += 1
            timings["upload_geotiffs"] = time.time() - t4
            timings["geotiff_count"] = geotiff_count

            # 4. Upload metadata using CloudTaskStaging
            t5 = time.time()
            staging = CloudTaskStaging(bucket=bucket, endpoint_url=endpoint_url)
            upload_result = staging.upload_artifacts(artifacts, output_prefix)
            manifest_uri = upload_result["manifest_uri"]
            timings["upload_metadata"] = time.time() - t5

        timings["total"] = time.time() - t0
        logger.info(
            "lambda_handler_complete",
            extra={
                "job_id": job_id,
                "chunk_id": chunk_id,
                "timings_ms": {
                    k: round(v * 1000, 2) if isinstance(v, float) else v
                    for k, v in timings.items()
                },
            },
        )

        return {
            "statusCode": 200,
            "manifest_uri": manifest_uri,
            "job_id": job_id,
            "chunk_id": chunk_id,
            "timings_ms": {
                k: round(v * 1000, 2) if isinstance(v, float) else v
                for k, v in timings.items()
            },
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
