"""EOIDS (Earth Observation Image Dataset) file naming and directory loading utilities.

Provides utilities for parsing, building paths, scanning directories, and loading
EOIDS data from local storage or cloud object storage.
"""

from .core import (
    EOIDSLoader,
    build_eoids_path,
    parse_eoids_filename,
    sanitize_job_name,
    scan_eoids_dir,
)

__all__ = [
    "EOIDSLoader",
    "build_eoids_path",
    "parse_eoids_filename",
    "sanitize_job_name",
    "scan_eoids_dir",
]
