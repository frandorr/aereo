# Choosing a Sensor

AEREO separates the core framework from search and I/O plugins. Pick the
plugins that match the satellite data you need.

## Sensor cheat sheet

| Sensor | Install | Search | Read | Reproject | Notes |
|---|---|---|---|---|---|
| **Sentinel-2 MSI** | `aereo aereo-search-planetary-computer` | `search_stac` | `read_odc_stac` | `reproject_odc` | Easiest starting point. |
| **VIIRS** | `aereo aereo-search-earthaccess aereo-read-satpy aereo-reproject-satpy` | `search_earthaccess` | `read_satpy` | `reproject_satpy` | NASA Earthdata login required. |
| **Sentinel-3 OLCI** | `aereo aereo-search-earthaccess aereo-read-satpy aereo-reproject-satpy` | `search_earthaccess` | `read_satpy` | `reproject_satpy` | NASA Earthdata login required. |
| **GOES ABI** | `aereo aereo-search-aws-goes aereo-read-satpy aereo-reproject-satpy` | `search_aws_goes` | `read_satpy` | `reproject_satpy` | Public AWS S3, no auth. |
| **GeoTessera** | `aereo aereo-search-tessera aereo-read-tessera` | `search_tessera` | `read_tessera` | — | Check catalog docs for auth. |

## When to use each reader

- **`read_odc_stac`** — for STAC-backed, analysis-ready data cubes (Sentinel-2
  L2A, Landsat, etc.). Uses `odc-stac` and returns an `xr.Dataset` aligned to
  the asset's native geobox.
- **`read_satpy`** — for swath or Level-1b data that needs Satpy-style scene
  reading and resampling (VIIRS, Sentinel-3, GOES).
- **`read_tessera`** — for GeoTessera tile catalogs.

## When to use each reprojector

- **`reproject_odc`** — reproject a raster `xr.Dataset` to a target CRS and
  resolution using `odc-geo`.
- **`reproject_satpy`** — resample swath data with Satpy's area definitions.
- **`reproject_swath`** — reproject 2-D lat/lon swaths to a UTM GeoBox using
  `odc-geo` and nearest-neighbor lookup.

## Next steps

- Follow the tutorial for your sensor in the [Examples](../examples/index.md)
  section.
- Read the [Search](search.md) guide for collection and band naming tips.
