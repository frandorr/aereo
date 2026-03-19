# Integrations

## External Data Sources

### NASA Earthdata
- **Auth**: `EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD` (via `aer-search-earthaccess` plugin)
- **Data**: VIIRS, MODIS granules via CMR API
- **Config**: `components/aer/settings/core.py`

### AWS S3 (GOES)
- **Auth**: `CDSE_S3_ACCESS_KEY`, `CDSE_S3_SECRET_KEY`, `CDSE_USER`, `CDSE_PASSWORD`
- **Access**: Via `s3fs` library
- **Data**: GOES satellite data via AWS/CDSE buckets

### EODC (European Open Data Cloud)
- **API URL**: `https://stac.eodc.eu/api/v1`
- **Collection**: `GFM` (Global Ferret Mask)
- **Storage**: ZARR format support

## File Formats

| Format | Library | Purpose |
|--------|---------|---------|
| HDF/HDF-EOS | `pyhdf` | MODIS, VIIRS Level 1 |
| GeoParquet | `pyarrow` + `geopandas` | Grid storage |
| ZARR | via GDAL | Cloud-native storage |
| GeoTIFF | via GDAL | Raster output |

## Spatial Processing

- **pyresample**: Area resampling, grid definitions
- **pyproj**: CRS transformations, UTM zone detection
- **shapely**: Geometry operations (intersection, buffering)

## Satellite Data Processing

- **satpy**: Reader framework for multiple satellite formats
- **python-geotiepoints**: Geolocation interpolation

## Authentication Patterns

```python
# Via Settings component
EARTHDATA_USERNAME=<user>
EARTHDATA_PASSWORD=<pass>
CDSE_S3_ACCESS_KEY=<key>
CDSE_S3_SECRET_KEY=<secret>
```

## Cloud-Native Settings

```python
# GDAL VSI for cloud raster access
GDAL_DISABLE_READDIR_ON_OPEN=YES
CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.tiff
VSI_CACHE=TRUE
VSI_CACHE_SIZE=256MB
GDAL_HTTP_MULTIRANGE=YES
GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES
GDAL_HTTP_TIMEOUT=30
```

## Key Configuration Locations

- `components/aer/settings/core.py` — All environment settings
- `projects/aer-core/pyproject.toml` — Core published dependencies
