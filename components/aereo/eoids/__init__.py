"""EOIDS (Earth Observation Image Dataset) file naming and directory loading utilities.

Provides utilities for parsing, building paths, scanning directories, and loading
EOIDS data from local storage or cloud object storage.
"""

from .core import (
    EOIDSLoader,
    build_eoids_path,
    parse_eoids_filename,
    scan_eoids_dir,
)

__all__ = [
    "build_eoids_path",
    "EOIDSLoader",
    "parse_eoids_filename",
    "scan_eoids_dir",
]
