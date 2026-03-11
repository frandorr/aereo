"""Core domain model for the generic downloader component.

Provides:
- ``DownloadedResultSchema``  — schema for tracking downloaded files.
- ``DownloadStatus``   — terminal status for a download attempt.
- ``s3_uri_to_https``  — utility to convert ``s3://`` URIs to downloadable HTTPS URLs.

The component is protocol-agnostic.
Concrete backends (e.g. ``downloader_aria2``, ``downloader_raw``) are provided as part of the main library.
"""

from __future__ import annotations

import enum
import shutil
from typing import Any
from urllib.parse import quote

import pandera.pandas as pa
from pandera.typing import Series
from structlog import get_logger

from aer.search import SearchResultSchema

logger = get_logger()


# ---------------------------------------------------------------------------
# Value objects / Schemas
# ---------------------------------------------------------------------------


class DownloadStatus(str, enum.Enum):
    """Terminal status for a download attempt."""

    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"


class DownloadedResultSchema(SearchResultSchema):
    """Schema for search results that have been processed by a downloader.

    Inherits all columns from SearchResultSchema and adds local_path and
    download_status.
    """

    local_path: Series[pa.String] = pa.Field(nullable=True)
    download_status: Series[pa.String] = pa.Field(
        isin=["complete", "failed", "skipped"], nullable=False
    )


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


# ---------------------------------------------------------------------------
# Smart download orchestrator
# ---------------------------------------------------------------------------


def download(
    gdf: pa.DataFrame["SearchResultSchema"] | Any,
    dest_dir: str
    | Any,  # using Any or specific Path to avoid extra imports here, though we can import them
    *,
    max_concurrent: int = 5,
    timeout: int = 600,
    verbose: bool = False,
    headers: dict[str, str] | None = None,
    options: dict[str, Any] | None = None,
    extra_args: list[str] | None = None,
    **kwargs: Any,
) -> pa.DataFrame["DownloadedResultSchema"] | Any:
    """Smart downloader that uses aria2 if available, or falls back to multithreaded raw HTTP.

    Args:
        gdf: DataFrame of search results to download.
        dest_dir: Local directory where files should be saved.
        max_concurrent: Max number of parallel downloads (default 5).
        timeout: Overall timeout in seconds (default 600).
        verbose: If ``True``, logs progress.
        headers: Optional mapping of extra HTTP headers (e.g. ``Authorization: Bearer …``).
        options: Backend-specific options.
        extra_args: Additional CLI flags.
        **kwargs: Reserved for forward compatibility.

    Returns:
        A new GeoDataFrame conforming to DownloadedResultSchema.
    """

    from aer.downloader_aria2 import download_aria2
    from aer.downloader_raw import download_raw

    if shutil.which("aria2c"):
        return download_aria2(
            gdf,
            dest_dir,
            max_concurrent=max_concurrent,
            timeout=timeout,
            verbose=verbose,
            headers=headers,
            options=options,
            extra_args=extra_args,
            **kwargs,
        )
    else:
        logger.warning("aria2c not found. Falling back to the raw python backend.")
        return download_raw(
            gdf,
            dest_dir,
            max_concurrent=max_concurrent,
            timeout=timeout,
            verbose=verbose,
            headers=headers,
            options=options,
            extra_args=extra_args,
            **kwargs,
        )
