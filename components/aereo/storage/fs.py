"""Filesystem storage backend for local file:// output URIs."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame

_ARTIFACTS_FILENAME = "artifacts.parquet"
_MANIFEST_FILENAME = "manifest.json"
_ARTIFACTS_URI_KEY = "artifacts_uri"


class FileSystemStorage:
    """Store artifact catalogs on the local filesystem."""

    def upload_artifacts(
        self,
        artifacts: GeoDataFrame[ArtifactSchema],
        output_prefix: str,
    ) -> dict[str, str]:
        """Write artifacts and a manifest under *output_prefix*."""
        prefix = _parse_file_uri(output_prefix)
        prefix.mkdir(parents=True, exist_ok=True)

        parquet_path = prefix / _ARTIFACTS_FILENAME
        artifacts.to_parquet(parquet_path)

        manifest = {_ARTIFACTS_URI_KEY: f"{output_prefix}{_ARTIFACTS_FILENAME}"}
        manifest_path = prefix / _MANIFEST_FILENAME
        manifest_path.write_text(json.dumps(manifest))

        return {"manifest_uri": f"{output_prefix}{_MANIFEST_FILENAME}"}

    def load_artifacts(
        self,
        manifest_uri: str,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Load artifacts referenced by a file:// manifest URI."""
        manifest_path = _parse_file_uri(manifest_uri)
        manifest = json.loads(manifest_path.read_text())

        artifacts_uri = manifest.get(_ARTIFACTS_URI_KEY)
        if not artifacts_uri:
            raise ValueError(f"Manifest missing '{_ARTIFACTS_URI_KEY}': {manifest}")

        artifacts_path = _parse_file_uri(artifacts_uri)
        df = gpd.read_parquet(artifacts_path)
        return GeoDataFrame[ArtifactSchema](df)


def _parse_file_uri(uri: str) -> Path:
    """Parse a file:// URI into a local Path."""
    if not uri.startswith("file://"):
        raise ValueError(f"Invalid file URI: {uri}")

    rest = uri[len("file://") :]
    if rest.startswith("/"):
        return Path(rest)

    host_sep = rest.find("/")
    if host_sep == -1:
        raise ValueError(f"Invalid file URI: {uri}")
    return Path(rest[host_sep:])
