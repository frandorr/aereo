"""
Generic download domain model. Defines typed download requests, a pluggable
DownloadMethod registry, and result types — without coupling to any specific
download backend (aria2, wget, etc.).
"""

from aer.downloader.core import (
    DownloadedResultSchema,
    DownloadStatus,
    download,
    s3_uri_to_https,
)

__all__ = [
    "DownloadedResultSchema",
    "DownloadStatus",
    "download",
    "s3_uri_to_https",
]
