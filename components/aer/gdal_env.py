"""GDAL environment configuration that MUST be imported before rasterio/odc-geo."""

from __future__ import annotations

import os
import warnings


def configure_gdal() -> None:
    """Set GDAL environment variables for optimal COG/VSICURL performance.

    This function should be called **before** any geospatial library
    (rasterio, odc-geo, osgeo) is imported so that the settings are
    picked up at module initialisation time.
    """
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
    os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
    os.environ.setdefault(
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.tiff,.vrt,.xml,.json"
    )


def setup_gdal_worker() -> None:
    """Configure GDAL environment variables once per process lifecycle.

    .. deprecated::
        Use :func:`configure_gdal` at process-start time instead.
        This function is kept for backward compatibility but no longer
        needed when ``configure_gdal()`` is called before geospatial
        imports.
    """
    warnings.warn(
        "setup_gdal_worker() is deprecated. "
        "Call configure_gdal() at process-start time instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    configure_gdal()
