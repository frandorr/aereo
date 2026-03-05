"""Core domain model for the generic downloader component.

Provides:
- ``DownloadRequest``  — a typed description of *what* to download and *where* to put it.
- ``DownloadResult``   — the outcome of a single download attempt.
- ``DownloadMethod``   — a pluggable registry (mirroring ``SearchMethod``) that resolves
  named download backends at runtime through entry-point plugins.
- ``s3_uri_to_https``  — utility to convert ``s3://`` URIs to downloadable HTTPS URLs.

The component is protocol-agnostic: it knows nothing about HTTP, S3, or aria2.
Concrete backends (e.g. ``downloader_aria2``) register themselves via the
``DownloadMethod.register`` decorator/function.
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any
from urllib.parse import quote

import attrs
from structlog import get_logger

logger = get_logger()


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class DownloadStatus(enum.Enum):
    """Terminal status for a download attempt."""

    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"


@attrs.frozen
class DownloadRequest:
    """Describes a single file to download.

    Attributes:
        uri: The source URI (``https://…``, ``s3://…``, or any scheme the
            backend understands).
        dest_dir: Local directory where the file should be saved.
        filename: Optional override for the saved file name.  When ``None``
            the backend should derive it from the URI.
        headers: Optional mapping of extra HTTP headers to send with the
            request (e.g. ``Authorization: Bearer …``).
        options: Backend-specific options forwarded as-is (e.g. aria2
            ``max-connection-per-server``).
    """

    uri: str
    dest_dir: Path = attrs.field(converter=Path)
    filename: str | None = None
    headers: dict[str, str] = attrs.Factory(dict)
    options: dict[str, Any] = attrs.Factory(dict)


@attrs.frozen
class DownloadResult:
    """Outcome of a download attempt.

    Attributes:
        request: The original request.
        status: Terminal status.
        path: Resolved filepath on disk (``None`` when *status* is ``FAILED``).
        error: Human-readable reason when *status* is ``FAILED``.
        bytes_downloaded: Number of bytes downloaded (0 when unknown).
    """

    request: DownloadRequest
    status: DownloadStatus
    path: Path | None = None
    error: str | None = None
    bytes_downloaded: int = 0


# ---------------------------------------------------------------------------
# URI utilities
# ---------------------------------------------------------------------------


def s3_uri_to_https(
    uri: str,
    endpoint_map: dict[str, str] | None = None,
) -> str:
    """Convert an ``s3://bucket/key`` URI to an HTTPS URL.

    If the bucket is found in *endpoint_map* the key is appended to the
    corresponding base URL.  Otherwise a generic AWS virtual-hosted-style
    URL is used as fallback.

    Non-S3 URIs are returned unchanged.

    Args:
        uri: An ``s3://…`` URI (or any other URI, which is returned as-is).
        endpoint_map: Mapping of ``bucket_name → base_https_url``.

    Returns:
        An HTTPS URL string.
    """
    if not uri.startswith("s3://"):
        return uri

    without_scheme = uri[5:]
    bucket, _, key = without_scheme.partition("/")
    endpoints = endpoint_map or {}

    if bucket in endpoints:
        base = endpoints[bucket].rstrip("/")
        safe_key = "/".join(quote(seg, safe="") for seg in key.split("/"))
        return f"{base}/{safe_key}"

    # Fallback: public AWS virtual-hosted-style URL
    safe_key = "/".join(quote(seg, safe="") for seg in key.split("/"))
    return f"https://{bucket}.s3.amazonaws.com/{safe_key}"
