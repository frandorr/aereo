from typing import Any
from unittest.mock import MagicMock, patch

from aereo.lambda_handler.core import handler


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


@patch("aereo.lambda_handler.core._serializer")
@patch("aereo.lambda_handler.core._runner")
@patch("aereo.lambda_handler.core.CloudTaskStaging")
def test_handler_success(
    mock_staging_class: MagicMock,
    mock_runner: MagicMock,
    mock_serializer: MagicMock,
):
    import sys

    mock_s3 = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_s3

    mock_staging = MagicMock()
    mock_staging.upload_artifacts.return_value = {
        "manifest_uri": "s3://bucket/results/0/manifest.json"
    }
    mock_staging_class.return_value = mock_staging

    event = {
        "task_uri": "s3://bucket/tasks/0/",
        "output_prefix": "s3://bucket/results/0/",
        "job_id": "job-123",
        "chunk_id": 5,
    }
    context: Any = MagicMock()

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        result = handler(event, context)

    assert result["statusCode"] == 200
    assert result["manifest_uri"] == "s3://bucket/results/0/manifest.json"
    assert result["job_id"] == "job-123"
    assert result["chunk_id"] == 5

    mock_boto3.client.assert_called_once_with("s3", endpoint_url=None)
    mock_serializer.deserialize.assert_called_once()
    mock_runner.run.assert_called_once()
    mock_staging_class.assert_called_once_with(bucket="bucket", endpoint_url=None)
    mock_staging.upload_artifacts.assert_called_once()
