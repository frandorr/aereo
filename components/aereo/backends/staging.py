"""Concrete TaskStaging implementation for S3 and Cloud backends."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import geopandas as gpd
from aereo.interfaces import TaskStaging
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame

logger = logging.getLogger(__name__)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split an s3:// URI into (bucket, key)."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    parts = uri[5:].split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key


class CloudTaskStaging(TaskStaging):
    """Staging helper that uploads/downloads tasks and artifacts to AWS S3 (and GCS in the future)."""

    def __init__(
        self, bucket: str, provider: str = "s3", endpoint_url: str | None = None
    ) -> None:
        if provider not in ("s3", "gcs"):
            raise ValueError(f"Unsupported provider: {provider}")
        if provider == "gcs":
            raise NotImplementedError("GCS support coming soon")

        self.bucket = bucket
        self.provider = provider
        self.endpoint_url = endpoint_url
        self._s3: Any | None = None

    def _client(self) -> Any:
        """Lazy boto3 S3 client (refreshed every call to avoid expired creds)."""
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
        """Upload serialized task files to S3 and return the task URI."""
        s3 = self._client()
        prefix = f"aereo-tasks/{job_id}/{task_idx}/"
        for file in Path(src_dir).iterdir():
            if file.is_file():
                key = f"{prefix}{file.name}"
                logger.debug(
                    "staging_upload", extra={"bucket": self.bucket, "key": key}
                )
                s3.upload_file(str(file), self.bucket, key)
        return f"s3://{self.bucket}/{prefix}"

    def result_prefix(self, job_id: str, task_idx: int) -> str:
        """Return the S3 URI prefix where the remote worker should write results."""
        return f"s3://{self.bucket}/results/{job_id}/{task_idx}/"

    def load_artifacts(self, manifest_uri: str) -> GeoDataFrame[ArtifactSchema]:
        """Download a manifest and its referenced artifacts from S3."""
        s3 = self._client()
        bucket, key = _parse_s3_uri(manifest_uri)

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            s3.download_file(bucket, key, str(manifest_path))
            manifest = json.loads(manifest_path.read_text())

        artifacts_uri = manifest.get("artifacts_uri")
        if not artifacts_uri:
            raise ValueError(f"Manifest missing 'artifacts_uri': {manifest}")

        bucket, key = _parse_s3_uri(artifacts_uri)
        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "artifacts.parquet"
            s3.download_file(bucket, key, str(parquet_path))
            df = gpd.read_parquet(parquet_path)

        return GeoDataFrame[ArtifactSchema](df)

    def upload_artifacts(
        self,
        artifacts: GeoDataFrame[ArtifactSchema],
        output_prefix: str,
    ) -> dict[str, str]:
        """Upload artifacts and a manifest to S3.

        Returns a dict with ``manifest_uri`` pointing at the uploaded manifest.
        """
        s3 = self._client()
        bucket, prefix = _parse_s3_uri(output_prefix)

        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "artifacts.parquet"
            artifacts.to_parquet(parquet_path)
            s3.upload_file(str(parquet_path), bucket, f"{prefix}artifacts.parquet")

            manifest = {"artifacts_uri": f"s3://{bucket}/{prefix}artifacts.parquet"}
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            s3.upload_file(str(manifest_path), bucket, f"{prefix}manifest.json")

        return {"manifest_uri": f"s3://{bucket}/{prefix}manifest.json"}
