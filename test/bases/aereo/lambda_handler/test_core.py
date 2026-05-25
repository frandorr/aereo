from typing import Any
from unittest.mock import MagicMock, patch

from aereo.lambda_handler.core import handler


@patch("aereo.lambda_handler.core.handle")
def test_handler_missing_task_uri(mock_handle: MagicMock):
    event = {"output_prefix": "s3://bucket/results/0/"}
    context: Any = MagicMock()
    result = handler(event, context)
    assert result["statusCode"] == 400
    assert "task_uri" in result["error"]
    mock_handle.assert_not_called()


@patch("aereo.lambda_handler.core.handle")
def test_handler_missing_output_prefix(mock_handle: MagicMock):
    event = {"task_uri": "s3://bucket/tasks/0/task_meta.json"}
    context: Any = MagicMock()
    result = handler(event, context)
    assert result["statusCode"] == 400
    assert "output_prefix" in result["error"]
    mock_handle.assert_not_called()


@patch("aereo.lambda_handler.core.handle")
def test_handler_delegates_to_extract_remote(mock_handle: MagicMock):
    mock_handle.return_value = {
        "statusCode": 200,
        "manifest_uri": "s3://bucket/results/0/manifest.json",
    }
    event = {
        "task_uri": "s3://bucket/tasks/0/task_meta.json",
        "output_prefix": "s3://bucket/results/0/",
    }
    context: Any = MagicMock()
    result = handler(event, context)

    mock_handle.assert_called_once_with(event, context)
    assert result["statusCode"] == 200
    assert result["manifest_uri"] == "s3://bucket/results/0/manifest.json"
