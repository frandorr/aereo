# aereo

> Plugin-based satellite data extraction — from search to analysis-ready Major TOM grid in minutes.

`aereo` is the core framework. Install it together with search and extract plugins for the sensors you need:

```bash
# GOES ABI (public S3, no auth)
pip install aereo aereo-search-aws-goes aereo-extract-satpy

# Sentinel-2 (Planetary Computer)
pip install aereo aereo-search-planetary-computer aereo-extract-odc-stac

# MODIS / VIIRS / Sentinel-3 (NASA Earthdata)
pip install aereo aereo-search-earthaccess aereo-extract-satpy
```

- **Search** across multiple satellite catalogs through a unified API.
- **Extract** assets and reproject them automatically to the same **Major TOM grid**.
- **Plugin-based** — add new sensors by installing pip packages; no code changes required.

For docs, examples, and plugin development guides, see [https://frandorr.github.io/aereo](https://frandorr.github.io/aereo).
