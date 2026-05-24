from typing import Any
from unittest.mock import MagicMock


from aer.lambda_handler.core import handler


def test_handler_missing_task_uri():
    event = {"output_prefix": "s3://bucket/results/0/"}
    context: Any = MagicMock()
    result = handler(event, context)
    assert result["statusCode"] == 400
    assert "task_uri" in result["error"]


def test_handler_missing_output_prefix():
    event = {"task_uri": "s3://bucket/tasks/0/task_meta.json"}
    context: Any = MagicMock()
    result = handler(event, context)
    assert result["statusCode"] == 400
    assert "output_prefix" in result["error"]


def test_handler_success():
    event = {
        "task_uri": "s3://bucket/tasks/0/task_meta.json",
        "output_prefix": "s3://bucket/results/0/",
    }
    context: Any = MagicMock()
    result = handler(event, context)
    assert result["statusCode"] == 200
    assert result["manifest_uri"] == "s3://bucket/results/0/manifest.json"
