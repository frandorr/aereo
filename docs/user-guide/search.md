# Search

Search providers turn a sensor catalog query into a validated
`GeoDataFrame[AssetSchema]`. AEREO ships with two built-in providers and
supports many more through plugins.

## Built-in providers

| Function | Best for | Typical catalogs |
|---|---|---|
| `search_stac` | Analysis-ready STAC collections | Planetary Computer, Earth Search, Element84 |
| `search_earthaccess` | NASA Earthdata holdings | VIIRS, MODIS, Sentinel-3 |

External plugins include `search_aws_goes` and `search_tessera`.

## Common arguments

All search providers accept a similar shape:

```python
assets = job.search(
    search_stac,
    collections={"sentinel-2-l2a": ["red", "nir"]},
    intersects="examples/config/aoi/chocon.geojson",
    start_datetime="2024-01-01T00:00:00Z",
    end_datetime="2024-01-10T23:59:59Z",
)
```

| Argument | Meaning |
|---|---|
| `collections` | Mapping of collection name to list of bands/assets, or a list of collection names. |
| `intersects` | Shapely geometry, GeoJSON dict, or path to a GeoJSON file. |
| `start_datetime` / `end_datetime` | Time window (datetime, ISO string, or `None`). |

## Collection and band names

Band names depend on the collection. A few common ones:

| Collection | Common bands |
|---|---|
| `sentinel-2-l2a` | `red`, `green`, `blue`, `nir`, `swir16`, `scl` |
| `landsat-c2-l2` | `red`, `green`, `blue`, `nir08`, `swir16` |

Use the band aliases that the reader plugin expects. `read_odc_stac` accepts
both common names and STAC asset keys.

## Search returns a validated DataFrame

The returned `GeoDataFrame[AssetSchema]` has one row per scene/granule and a
`geometry` column with the asset footprint. You can inspect it like any
GeoPandas object:

```python
print(assets.head())
assets.plot()
```

## Authentication

- **Planetary Computer** — set a subscription key via environment variable or
  pass it to the search provider.
- **NASA Earthdata** — use `earthaccess.login()` or set `EARTHDATA_USERNAME`
  and `EARTHDATA_PASSWORD`.

See [Install](../install.md) for links and setup details.
