"""Storage backends for extraction results.

Provides a protocol and a URI-scheme dispatcher so callers can write results to
local filesystems, S3, or future object stores without changing the rest of the
pipeline.
"""

from __future__ import annotations

from typing import Protocol

from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


class StorageBackend(Protocol):
    """Write/read extraction results to/from a URI-addressable store."""

    def upload_artifacts(
        self,
        artifacts: GeoDataFrame[ArtifactSchema],
        output_prefix: str,
    ) -> dict[str, str]:
        """Upload artifacts and a manifest; return {"manifest_uri": ...}."""
        ...

    def load_artifacts(
        self,
        manifest_uri: str,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Load artifacts referenced by a manifest URI."""
        ...


def storage_for_uri(uri: str) -> StorageBackend:
    """Return a storage backend for a URI scheme."""
    if uri.startswith("s3://"):
        from aereo.storage.s3 import S3Storage

        return S3Storage()
    if uri.startswith("file://"):
        from aereo.storage.fs import FileSystemStorage

        return FileSystemStorage()
    raise ValueError(f"Unsupported URI scheme: {uri}")
