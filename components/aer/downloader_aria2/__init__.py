"""
Aria2-based download backend. Downloads files via HTTP/HTTPS
in parallel using the aria2c CLI.
"""

from aer.downloader_aria2.core import download_aria2, DOWNLOAD_ARIA2

__all__ = ["download_aria2", "DOWNLOAD_ARIA2"]
