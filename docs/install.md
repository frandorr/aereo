# Install

Pick your sensor and copy-paste the install command.

## GOES ABI (public S3, no auth)

```bash
pip install aereo aereo-search-aws-goes aereo-extract-satpy
```

## Sentinel-2 (Planetary Computer)

```bash
pip install aereo aereo-search-planetary-computer aereo-extract-odc-stac
```

## MODIS / VIIRS / Sentinel-3 (NASA Earthdata)

```bash
pip install aereo aereo-search-earthaccess aereo-extract-satpy
```

> **Note:** The PyPI package is `aereo` because `aereo` is already taken.

These plugins ship ready to use. AEREO's architecture makes adding new sensors trivial — a **search plugin** connects the catalog, an **extract plugin** handles the assets, and reprojection to the **Major TOM grid** happens automatically.
