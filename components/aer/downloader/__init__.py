"""
Generic download domain model. Defines typed download requests,
result types — without coupling to any specific
download backend (aria2, wget, etc.).
"""

from aer.downloader.core import (
    DownloadedResultSchema,
    DownloadStatus,
    s3_uri_to_https,
)

__all__ = [
    "DownloadedResultSchema",
    "DownloadStatus",
    "s3_uri_to_https",
]
