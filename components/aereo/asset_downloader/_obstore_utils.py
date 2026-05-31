"""Internal helpers for resolving URLs to obstore stores."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _resolve_store(
    href: str, store_options: dict[str, Any] | None = None
) -> tuple[Any, str]:
    """Parse *href* and return an (obstore_store, path) pair.

    Supported schemes:
      - ``s3://bucket/path``        → ``S3Store("bucket")``, ``"path"``
      - ``gs://bucket/path``        → ``GCSStore("bucket")``, ``"path"``
      - ``az://account/container/path`` → ``AzureStore(account, container)``, ``"path"``
      - ``http(s)://host/path``     → ``HTTPStore.from_url(base)``, ``"relative/path"``
      - ``file:///path`` or bare path → ``LocalStore()``, ``"/path"``

    Args:
        href: URL or path to resolve.
        store_options: Optional dict of keyword arguments forwarded to the
            obstore store constructor.  For ``s3://`` URLs this is passed as
            ``S3Store(bucket, **store_options)``; for ``gs://`` as
            ``GCSStore(bucket, **store_options)``; etc.

    Raises:
        ValueError: If the URL scheme is unsupported.
    """
    parsed = urlparse(href)
    opts = dict(store_options or {})

    if parsed.scheme == "s3":
        from obstore.store import S3Store

        bucket = parsed.netloc
        path = parsed.path.lstrip("/")
        # Default to anonymous access unless the caller overrides it.
        if "skip_signature" not in opts:
            opts["skip_signature"] = True
        # Public NOAA GOES buckets are in us-east-1; avoid cross-region
        # redirect errors by setting the correct region.
        if bucket.startswith("noaa-goes") and "region" not in opts:
            opts["region"] = "us-east-1"
        return S3Store(bucket, **opts), path  # type: ignore[reportCallIssue]

    if parsed.scheme == "gs":
        from obstore.store import GCSStore

        bucket = parsed.netloc
        path = parsed.path.lstrip("/")
        return GCSStore(bucket, **opts), path  # type: ignore[reportCallIssue]

    if parsed.scheme == "az":
        from obstore.store import AzureStore

        # az://account/container/path
        parts = parsed.path.lstrip("/").split("/", 1)
        if len(parts) < 2:
            raise ValueError(
                f"Azure URL must be az://account/container/path, got: {href}"
            )
        account, container = parts[0], parts[1].split("/", 1)[0]
        path = parts[1].split("/", 1)[1] if "/" in parts[1] else ""
        return AzureStore(container, account_name=account, **opts), path  # type: ignore[reportCallIssue]

    if parsed.scheme in ("http", "https"):
        from obstore.store import HTTPStore

        # Use the full URL as the store base; path is empty because the
        # entire href is the object location.
        store = HTTPStore.from_url(href, **opts)
        return store, ""

    if parsed.scheme == "file":
        from obstore.store import LocalStore

        path = parsed.path
        return LocalStore(**opts), path

    # Bare local path (no scheme)
    if Path(href).exists() or Path(href).is_absolute():
        from obstore.store import LocalStore

        return LocalStore(**opts), str(Path(href))

    raise ValueError(
        f"Unsupported URL scheme or path: {href}. "
        "Supported: s3://, gs://, az://, http(s)://, file://, or local path."
    )


def _stream_obstore_to_disk(store: Any, path: str, local_path: Path) -> None:
    """Stream bytes from an obstore store to a local file.

    Uses obstore's top-level ``get()`` function and writes chunks
    without materialising the whole object in memory.
    """
    import obstore

    local_path.parent.mkdir(parents=True, exist_ok=True)
    result = obstore.get(store, path)
    with open(local_path, "wb") as f:
        for chunk in result:
            f.write(chunk)
