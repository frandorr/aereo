"""S3 storage backend for s3:// output URIs."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import geopandas as gpd
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame

_ARTIFACTS_FILENAME = "artifacts.parquet"
_MANIFEST_FILENAME = "manifest.json"
_ARTIFACTS_URI_KEY = "artifacts_uri"


class S3Storage:
    """Store artifact catalogs in AWS S3 or S3-compatible object stores."""

    def __init__(self, endpoint_url: str | None = None) -> None:
        self.endpoint_url = endpoint_url
        self._s3: Any | None = None

    def _client(self) -> Any:
        """Return a lazily-initialised boto3 S3 client."""
        try:
            import boto3  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for S3Storage. Install it with: pip install boto3"
            ) from exc
        self._s3 = boto3.client("s3", endpoint_url=self.endpoint_url)
        return self._s3

    def upload_artifacts(
        self,
        artifacts: GeoDataFrame[ArtifactSchema],
        output_prefix: str,
    ) -> dict[str, str]:
        """Upload artifacts and a manifest to S3."""
        bucket, prefix = _parse_s3_uri(output_prefix)
        s3 = self._client()

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

    def load_artifacts(
        self,
        manifest_uri: str,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Download a manifest and its referenced artifacts from S3."""
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


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split an s3:// URI into (bucket, key)."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    parts = uri[5:].split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key
