"""Raw Python multithreaded download backend.

Downloads files via HTTP/HTTPS using the standard library `urllib` and `concurrent.futures`.
It behaves identically to `downloader_aria2` but requires no external binaries.
"""

from aer.downloader_raw.core import download_raw

__all__ = ["download_raw"]
