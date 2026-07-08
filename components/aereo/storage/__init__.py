"""Storage backends for extraction results."""

from aereo.storage.core import StorageBackend, storage_for_uri
from aereo.storage.fs import FileSystemStorage
from aereo.storage.s3 import S3Storage

__all__ = ["FileSystemStorage", "S3Storage", "StorageBackend", "storage_for_uri"]
