"""Entrypoint for the aereo-extract runtime."""

from __future__ import annotations

import json
import logging
import os
import sys

from aereo_extract.handlers import handle_http, handle_lambda


def _configure_logging() -> None:
    """Set up basic structured logging for the container."""
    level = os.environ.get("AEREO_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


def main() -> None:
    """Dispatch to HTTP or Lambda runtime depending on environment."""
    _configure_logging()

    if os.environ.get("AWS_LAMBDA_RUNTIME_API"):
        # When this script is used as the Lambda handler directly (non-RIE),
        # run a minimal runtime loop. In practice the AWS Lambda base image
        # usually invokes handle_lambda(event, context) directly via the RIC.
        _run_lambda_runtime_loop()
    else:
        handle_http(
            host=os.environ.get("AEREO_EXTRACT_HOST", "0.0.0.0"),
            port=int(os.environ.get("AEREO_EXTRACT_PORT", "8080")),
        )


def _run_lambda_runtime_loop() -> None:
    """Minimal AWS Lambda runtime loop.

    Fetches invocation events from the Lambda runtime API and posts responses.
    """
    import urllib.request

    runtime_api = os.environ["AWS_LAMBDA_RUNTIME_API"]
    next_url = f"http://{runtime_api}/2018-06-01/runtime/invocation/next"

    while True:
        try:
            with urllib.request.urlopen(next_url) as resp:
                request_id = resp.headers["Lambda-Runtime-Aws-Request-Id"]
                event = json.loads(resp.read().decode("utf-8"))
                result = handle_lambda(event, None)
                response_url = (
                    f"http://{runtime_api}/2018-06-01/runtime/invocation/"
                    f"{request_id}/response"
                )
                data = json.dumps(result, default=str).encode("utf-8")
                req = urllib.request.Request(
                    response_url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req)
        except Exception:
            logging.getLogger(__name__).exception("lambda_runtime_loop_error")
            # The runtime loop must continue; Lambda will manage the process.
            raise


if __name__ == "__main__":
    main()
