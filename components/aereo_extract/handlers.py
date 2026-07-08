"""HTTP and Lambda request handlers for aereo-extract.

The :func:`handle_lambda` entrypoint is invoked by the AWS Lambda runtime.
The :func:`handle_http` entrypoint starts a local HTTP server on port 8080.
Both call :func:`handle_event`, which accepts either a direct base64-encoded
zip task payload or a staged ``task_uri``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import attrs
from aereo.execution import run_task
from aereo.executors._serialization import _TaskSerializer
from aereo.interfaces import ExtractionTask
from aereo.storage import storage_for_uri

logger = logging.getLogger(__name__)

_S3_PREFIX = "s3://"

_serializer = _TaskSerializer()


def _error_response(
    error: Exception,
    job_id: str = "unknown",
    task_id: str = "unknown",
    status_code: int = 500,
) -> dict[str, Any]:
    """Build a standardized error response dict."""
    return {
        "statusCode": status_code,
        "error": str(error),
        "error_type": type(error).__name__,
        "job_id": job_id,
        "task_id": task_id,
        "manifest_uri": None,
    }


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split an s3:// URI into (bucket, key)."""
    if not uri.startswith(_S3_PREFIX):
        raise ValueError(f"Invalid S3 URI: {uri}")
    parts = uri[len(_S3_PREFIX) :].split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key


def _download_prefix(s3: Any, bucket: str, prefix: str, dest_dir: Path) -> None:
    """Download all objects under *prefix* into *dest_dir*."""
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


def _load_direct_task(event: dict[str, Any]) -> ExtractionTask:
    """Deserialize a base64 zip task from a direct payload."""
    task_b64 = event.get("task")
    if not task_b64:
        raise ValueError("Missing 'task' field for direct mode")
    task_bytes = base64.b64decode(task_b64)
    return _serializer.deserialize_from_bytes(task_bytes)


def _load_staged_task(event: dict[str, Any]) -> ExtractionTask:
    """Download and deserialize a task staged on S3."""
    task_uri = event.get("task_uri")
    if not task_uri:
        raise ValueError("Missing 'task_uri' field for staged mode")
    bucket, prefix = _parse_s3_uri(task_uri)

    import boto3  # pyright: ignore[reportMissingImports]

    s3 = boto3.client("s3", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
    with tempfile.TemporaryDirectory() as tmpdir:
        task_dir = Path(tmpdir)
        _download_prefix(s3, bucket, prefix, task_dir)
        return _serializer.deserialize(task_dir)


def _load_task(event: dict[str, Any]) -> ExtractionTask:
    """Load a task using either direct or staged mode."""
    mode = event.get("mode")
    if mode == "direct":
        return _load_direct_task(event)
    if mode == "staged" or event.get("task_uri"):
        return _load_staged_task(event)
    raise ValueError("Payload must include 'mode'/'task' or 'task_uri'")


def handle_event(event: dict[str, Any]) -> dict[str, Any]:
    """Process a single extraction request.

    Args:
        event: Dictionary with mode, task/task_uri, output_prefix, job_id,
            chunk_id.

    Returns:
        Response dict with statusCode and manifest_uri, or error details.
    """
    output_prefix = event.get("output_prefix", "")
    job_id = event.get("job_id", "unknown")
    task_id = event.get("task_id", "unknown")

    logger.info(
        "aereo_extract_request",
        extra={"job_id": job_id, "task_id": task_id, "mode": event.get("mode")},
    )

    if not output_prefix:
        return _error_response(
            ValueError("Missing required field: output_prefix"),
            job_id,
            task_id,
            status_code=400,
        )

    try:
        task = _load_task(event)
    except Exception as exc:
        logger.exception("failed_to_load_task")
        return _error_response(exc, job_id, task_id, status_code=400)

    try:
        # Ensure results are written to the requested output prefix.  For local
        # file:// URIs we strip the scheme so the orchestrator sees a plain path.
        output_uri = output_prefix
        if output_uri.startswith("file://"):
            output_uri = output_uri[len("file://") :]
        task = attrs.evolve(
            task,
            job=task.job.model_copy(update={"output_uri": output_uri}),
        )

        artifacts = run_task(task)
        storage = storage_for_uri(output_prefix)
        result = storage.upload_artifacts(artifacts, output_prefix)

        return {
            "statusCode": 200,
            "manifest_uri": result["manifest_uri"],
            "job_id": job_id,
            "task_id": task_id,
        }
    except Exception as exc:
        logger.exception("extraction_failed")
        return _error_response(exc, job_id, task_id, status_code=500)


def handle_lambda(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler entrypoint.

    Args:
        event: Lambda event dictionary.
        context: Lambda runtime context.

    Returns:
        Response dict for the Lambda runtime.
    """
    return handle_event(event)


class _HTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for /health and /extract."""

    def _send_json(self, status_code: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/extract":
            self._send_json(404, {"error": "not found"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            event = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._send_json(400, _error_response(exc, status_code=400))
            return

        response = handle_event(event)
        status_code = response.get("statusCode", 200)
        self._send_json(status_code, response)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.info(format, *args)


def handle_http(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start a local HTTP server for extraction requests."""
    server = HTTPServer((host, port), _HTTPHandler)
    logger.info(
        "aereo_extract_http_server_listening", extra={"host": host, "port": port}
    )
    server.serve_forever()
