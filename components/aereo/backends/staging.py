"""Concrete TaskStaging implementation for S3 and cloud object storage."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import geopandas as gpd
from aereo.interfaces import TaskStaging
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()

__all__ = ["CloudTaskStaging"]

_TASK_PREFIX = "aereo-tasks/"
_RESULTS_PREFIX = "results/"
_ARTIFACTS_FILENAME = "artifacts.parquet"
_MANIFEST_FILENAME = "manifest.json"
_ARTIFACTS_URI_KEY = "artifacts_uri"


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split an s3:// URI into (bucket, key).

    Args:
        uri: A valid S3 URI starting with ``s3://``.

    Returns:
        A 2-tuple of ``(bucket, key)``.

    Raises:
        ValueError: If *uri* does not start with ``s3://``.
    """
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    parts = uri[5:].split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key


class CloudTaskStaging(TaskStaging):
    """Staging helper that uploads and downloads tasks and artifacts to AWS S3.

    GCS support is planned but not yet implemented.
    """

    def __init__(
        self, bucket: str, provider: str = "s3", endpoint_url: str | None = None
    ) -> None:
        """Create a new CloudTaskStaging instance.

        Args:
            bucket: Name of the S3 bucket to use.
            provider: Cloud provider. Only ``"s3"`` is supported; ``"gcs"`` raises
                :class:`NotImplementedError`.
            endpoint_url: Optional custom endpoint URL (e.g. for LocalStack).

        Raises:
            ValueError: If *provider* is not ``"s3"`` or ``"gcs"``.
            NotImplementedError: If *provider* is ``"gcs"``.
        """
        if provider not in ("s3", "gcs"):
            raise ValueError(f"Unsupported provider: {provider}")
        if provider == "gcs":
            raise NotImplementedError("GCS support coming soon")

        self.bucket = bucket
        self.provider = provider
        self.endpoint_url = endpoint_url
        self._s3: Any | None = None

    def _client(self) -> Any:
        """Return a lazily-initialised boto3 S3 client.

        The client is recreated on every call to avoid expired credentials.

        Returns:
            A boto3 S3 client object.

        Raises:
            ImportError: If ``boto3`` is not installed.
        """
        try:
            import boto3  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for S3/CloudTaskStaging. "
                "Install it with: pip install boto3"
            ) from exc
        self._s3 = boto3.client("s3", endpoint_url=self.endpoint_url)
        return self._s3

    def stage(self, src_dir: Path, job_id: str, task_idx: int) -> str:
        """Upload serialized task files to S3.

        Args:
            src_dir: Local directory containing the serialized task files.
            job_id: Identifier for the parent job.
            task_idx: Index of the task within the job.

        Returns:
            The S3 URI prefix where the files were uploaded.
        """
        s3 = self._client()
        prefix = f"{_TASK_PREFIX}{job_id}/{task_idx}/"
        for file in src_dir.iterdir():
            if file.is_file():
                key = f"{prefix}{file.name}"
                logger.debug(
                    "staging_upload",
                    bucket=self.bucket,
                    key=key,
                )
                s3.upload_file(str(file), self.bucket, key)
        return f"s3://{self.bucket}/{prefix}"

    def result_prefix(self, job_id: str, task_idx: int) -> str:
        """Return the S3 URI prefix where the remote worker should write results.

        Args:
            job_id: Identifier for the parent job.
            task_idx: Index of the task within the job.

        Returns:
            An S3 URI prefix ending with ``/``.
        """
        return f"s3://{self.bucket}/{_RESULTS_PREFIX}{job_id}/{task_idx}/"

    def load_artifacts(self, manifest_uri: str) -> GeoDataFrame[ArtifactSchema]:
        """Download a manifest and its referenced artifacts from S3.

        Args:
            manifest_uri: S3 URI of the manifest JSON file.

        Returns:
            A ``GeoDataFrame[ArtifactSchema]`` containing the downloaded artifacts.

        Raises:
            ValueError: If the manifest is missing the ``artifacts_uri`` key.
        """
        s3 = self._client()
        bucket, key = _parse_s3_uri(manifest_uri)

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / _MANIFEST_FILENAME
            s3.download_file(bucket, key, str(manifest_path))
            manifest = json.loads(manifest_path.read_text())

        artifacts_uri = manifest.get(_ARTIFACTS_URI_KEY)
        if not artifacts_uri:
            raise ValueError(f"Manifest missing '{_ARTIFACTS_URI_KEY}': {manifest}")

        bucket, key = _parse_s3_uri(artifacts_uri)
        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / _ARTIFACTS_FILENAME
            s3.download_file(bucket, key, str(parquet_path))
            df = gpd.read_parquet(parquet_path)

        return GeoDataFrame[ArtifactSchema](df)

    def upload_artifacts(
        self,
        artifacts: GeoDataFrame[ArtifactSchema],
        output_prefix: str,
    ) -> dict[str, str]:
        """Upload artifacts and a manifest to S3.

        Args:
            artifacts: GeoDataFrame containing the artifacts to upload.
            output_prefix: S3 URI prefix where files should be written.

        Returns:
            A dict with ``manifest_uri`` pointing at the uploaded manifest.
        """
        s3 = self._client()
        bucket, prefix = _parse_s3_uri(output_prefix)

        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / _ARTIFACTS_FILENAME
            artifacts.to_parquet(parquet_path)
            s3.upload_file(str(parquet_path), bucket, f"{prefix}{_ARTIFACTS_FILENAME}")

            manifest = {
                _ARTIFACTS_URI_KEY: f"s3://{bucket}/{prefix}{_ARTIFACTS_FILENAME}"
            }
            manifest_path = Path(tmpdir) / _MANIFEST_FILENAME
            manifest_path.write_text(json.dumps(manifest))
            s3.upload_file(str(manifest_path), bucket, f"{prefix}{_MANIFEST_FILENAME}")

        return {"manifest_uri": f"s3://{bucket}/{prefix}{_MANIFEST_FILENAME}"}
