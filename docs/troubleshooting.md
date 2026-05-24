# Troubleshooting

This page distills the most common failures and their fixes. If you hit a problem not listed here, check the [examples README](examples/README.md) for sensor-specific pitfalls or open an issue on GitHub.

---

## 1. Installation issues

### `aer-eo` vs `aer`

The PyPI package is **`aer-eo`** because the name `aer` is already taken by another project.

```bash
# ✅ Correct
pip install aer-eo

# ❌ Wrong
pip install aer
```

### Missing plugins

AER is a plugin-based framework. Installing only `aer-eo` gives you the core client and interfaces, but you cannot search or extract anything without at least one search plugin and one extract plugin.

**Symptom:**
```
PluginNotFoundError: No search plugin found for collection ...
```

**Fix:** Install the plugins for your sensor:

```bash
# GOES ABI (public S3, no auth)
pip install aer-search-aws-goes aer-extract-satpy

# Sentinel-2 (Planetary Computer)
pip install aer-search-planetary-computer aer-extract-odc-stac

# NASA sensors (MODIS, VIIRS, Sentinel-3)
pip install aer-search-earthaccess aer-extract-satpy
```

Verify what is installed:

```bash
aer plugins
```

---

## 2. Search returns empty

### Wrong collection name

Collection names are case-sensitive and vary by data provider.

| Provider | Wrong | Correct |
|----------|-------|---------|
| Sentinel-2 | `sentinel-2-l1c` | `sentinel-2-l2a` |
| GOES ABI | `ABI-L1B-RADF` | `ABI-L1b-RadF` |

### Missing `search_params`

GOES ABI requires `search_params={"satellite": "GOES-19"}` (or `GOES-18`, `GOES-16`). Without it, the search plugin may return results for the wrong satellite or nothing at all.

```python
AerProfile(
    name="goes_c02",
    resolution=1000,
    collections={"ABI-L1b-RadF": ["C02"]},
    search_params={"satellite": "GOES-19"},  # ✅ Required
    plugin_hints={"search": "search_aws_goes"},
)
```

### Date range too narrow

Some sensors have infrequent revisit times. A 10-minute window may contain zero granules. Try widening to a few hours or a full day.

---

## 3. Plugin not found

### Old plugin names

Plugin names were simplified in recent releases. If you are following an old blog post or notebook, you may see deprecated names.

| Old name | Current name |
|----------|--------------|
| `search_pc_sentinel2` | `search_planetary_computer` |
| `extract_pc_sentinel2` | `extract_odc_stac` |

### Missing pip install

Even if the plugin name is correct, the package must be installed in the same environment as `aer-eo`.

```bash
# Verify the plugin is importable
python -c "import aer_search_aws_goes"
```

If this raises `ModuleNotFoundError`, install the package.

---

## 4. Extraction fails

### Missing `reader` in `extract_params`

Satpy-based extractors need to know which reader to use. Without it, you get:

```
ReaderNotAvailable: No reader found for ...
```

**Fix:** Add the correct `reader` to `extract_params`:

| Sensor | Reader |
|--------|--------|
| GOES ABI | `abi_l1b` |
| VIIRS | `viirs_l1b` |
| Sentinel-3 OLCI | `olci_l1b` |

```python
AerProfile(
    ...,
    extract_params={"reader": "abi_l1b", "calibration": "reflectance"},
)
```

### Missing `downloader`

NASA Earthdata assets require a downloader because the URLs are behind URS authentication.

**Symptom:** Assets are found during search but extraction fails with HTTP 401 or "cannot open file" errors.

**Fix:** Add the Earthdata downloader to the profile:

```python
AerProfile(
    ...,
    downloader="aer.search_earthaccess.earthaccess_download_wrapper",
)
```

### Out of memory (OOM)

Large mosaics or high-resolution extractions can exhaust RAM.

**Fixes:**
- Reduce `cells_per_chunk` (e.g., `1` instead of `50`).
- Reduce `max_workers` (e.g., `1` instead of `8`).
- Use a smaller AOI or coarser `target_grid_dist`.
- Process one profile at a time instead of multiple sensors in parallel.

---

## 5. Output looks wrong

### Grid cell size

The default `target_grid_dist` is 256 km. If your AOI is a small city, a 256 km cell will include a lot of surrounding area.

**Fix:** Use a smaller cell size:

```python
GridConfig(target_grid_dist=50_000)  # 50 km cells
```

### CRS mismatch

Each grid cell is naturally projected to its local UTM zone. Adjacent cells may have different CRSs. When you mosaic them, AER reprojects everything to a common CRS, but if you open individual cells manually, expect varying CRS values.

### `conform_to` vs natural shapes

By default, each cell's output matches its natural UTM footprint, so adjacent cells tile edge-to-edge with no gaps.

When you set `conform_to=(W, H)`, every cell is padded to the same pixel dimensions with `NaN` fill. This is essential for ML pipelines but creates padding borders that do not exist in natural-shape mode.

| Mode | Use case | Edge behaviour |
|------|----------|----------------|
| Natural (default) | Visualization, mosaics | Seamless tiling |
| `conform_to` | ML training, fixed tensors | `NaN` padding where data is missing |

Remember: `conform_to` is `(width, height)`, matching rasterio's `(bands, height, width)` convention.

---

## Quick reference: exit codes

| Exit code | Meaning |
|-----------|---------|
| `0` | Success |
| `1` | Error (invalid config, missing file, extraction failure) |
| `2` | No search results found |
