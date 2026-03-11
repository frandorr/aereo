"""
Public download API that auto-selects the best available backend
(aria2 or raw Python). Consumes downloader_aria2 and downloader_raw
components.
"""

from aer.download_api.core import download

__all__ = ["download"]
