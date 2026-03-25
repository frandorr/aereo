from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

BASE_DIR = Path(__file__).parent


class Settings(BaseSettings):  # type: ignore[misc]
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="allow",
    )

    SATPY_CONFIG_PATH: str = os.pathsep.join(
        [
            str(
                BASE_DIR.parent / "satpy_readers"
            ),  # add more here if needed, like satpy_composites
        ]
    )
    NODATA: float = -1.0
    NODATA_UINT8: int = 255

    # Auth related (Optional in core, to be provided by user/plugin)
    EARTHDATA_USERNAME: str | None = None
    EARTHDATA_PASSWORD: str | None = None

    EODC_API_URL: str = "https://stac.eodc.eu/api/v1"
    EODC_GFM_COLLECTION_ID: str = "GFM"
    GDAL_DISABLE_READDIR_ON_OPEN: str = "YES"
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS: str = ".tif,.tiff"
    VSI_CACHE: str = "TRUE"
    VSI_CACHE_SIZE: str = str(256 * 1024 * 1024)  # 256 MB
    GDAL_HTTP_MULTIRANGE: str = "YES"
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES: str = "YES"
    GDAL_HTTP_TIMEOUT: str = "30"
    ZARR_STORE_SPEC_VERSION: str = "1.0"

    # Store and Cache Paths (Optional with defaults/None)
    AOD_STORE_PATH: Path | None = None
    SATPY_CACHE_DIR: Path | None = None
    SATPY_CACHE_SENSOR_ANGLES: bool = True
    SATPY_CACHE_LONLATS: bool = True

    CDSE_S3_ACCESS_KEY: str | None = None
    CDSE_S3_SECRET_KEY: str | None = None
    CDSE_USER: str | None = None
    CDSE_PASSWORD: str | None = None

    GRID_STORE_PATH: Path | None = None


def apply_runtime_env(settings: Settings) -> None:
    """Apply settings to environment variables for external libraries (GDAL, Earthdata, etc.)."""
    env_map = {
        "SATPY_CONFIG_PATH": settings.SATPY_CONFIG_PATH,
        "GDAL_DISABLE_READDIR_ON_OPEN": settings.GDAL_DISABLE_READDIR_ON_OPEN,
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": settings.CPL_VSIL_CURL_ALLOWED_EXTENSIONS,
        "VSI_CACHE": settings.VSI_CACHE,
        "VSI_CACHE_SIZE": settings.VSI_CACHE_SIZE,
        "GDAL_HTTP_TIMEOUT": settings.GDAL_HTTP_TIMEOUT,
    }

    if settings.SATPY_CACHE_DIR:
        env_map["SATPY_CACHE_DIR"] = str(settings.SATPY_CACHE_DIR)
        env_map["SATPY_CACHE_SENSOR_ANGLES"] = str(settings.SATPY_CACHE_SENSOR_ANGLES)
        env_map["SATPY_CACHE_LONLATS"] = str(settings.SATPY_CACHE_LONLATS)

    if settings.EARTHDATA_USERNAME:
        env_map["EARTHDATA_USERNAME"] = settings.EARTHDATA_USERNAME
    if settings.EARTHDATA_PASSWORD:
        env_map["EARTHDATA_PASSWORD"] = settings.EARTHDATA_PASSWORD

    for k, v in env_map.items():
        os.environ[k] = v


ENV_SETTINGS = Settings()
apply_runtime_env(ENV_SETTINGS)
