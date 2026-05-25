"""AER Lambda handler entrypoint."""

from __future__ import annotations

import logging
from typing import Any

from aereo_extract_remote.lambda_handler import handle

logger = logging.getLogger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AER Lambda handler entrypoint.

    Delegates to :func:`aereo_extract_remote.lambda_handler.handle` for
    deserialization, execution, and result upload.

    Expected event schema (defined by LambdaBackend)::

        {
            "task_uri": "s3://bucket/aer-tasks/job_id/0/task_meta.json",
            "output_prefix": "s3://bucket/results/job_id/0/"
        }

    Returns::

        {"statusCode": 200, "manifest_uri": "s3://bucket/results/job_id/0/manifest.json"}
    """
    logger.info("aer_lambda_invoked", extra={"event": event})

    task_uri = event.get("task_uri")
    output_prefix = event.get("output_prefix")

    if not task_uri or not output_prefix:
        return {
            "statusCode": 400,
            "error": "Missing required fields: task_uri, output_prefix",
        }

    return handle(event, context)
