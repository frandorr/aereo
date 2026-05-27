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

---

## Troubleshooting

### `PluginNotFoundError: No search plugin found for collection ...`

AEREO is a plugin-based framework. Installing only `aereo` gives you the core client and interfaces, but you cannot search or extract anything without at least one search plugin and one extract plugin.

**Fix:** Install the plugins for your sensor (see commands above) and verify:

```bash
aereo plugins
```

If a plugin is missing, install the corresponding pip package and run the command again. Even if the plugin name is correct, the package must be installed in the same environment as `aereo`:

```bash
python -c "import aereo_search_aws_goes"
```

If this raises `ModuleNotFoundError`, install the package.

### Old plugin names

Plugin names were simplified in recent releases. If you are following an old blog post or notebook, you may see deprecated names.

| Old name | Current name |
|----------|--------------|
| `search_pc_sentinel2` | `search_planetary_computer` |
| `extract_pc_sentinel2` | `extract_odc_stac` |
