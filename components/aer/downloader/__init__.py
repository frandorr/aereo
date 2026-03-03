"""
Generic download domain model. Defines typed download requests, a pluggable
DownloadMethod registry, and result types — without coupling to any specific
download backend (aria2, wget, etc.).
"""

from aer.downloader.core import (
    DownloadFunction,
    DownloadMethod,
    DownloadRequest,
    DownloadResult,
    DownloadStatus,
    s3_uri_to_https,
)

__all__ = [
    "DownloadFunction",
    "DownloadMethod",
    "DownloadRequest",
    "DownloadResult",
    "DownloadStatus",
    "s3_uri_to_https",
]
