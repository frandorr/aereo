# AER Examples

Runnable `.py` examples (with `# %%` cell markers for Jupyter compatibility) demonstrating the AER (Asset Extraction and Retrieval) framework for satellite data processing.

---

## Before You Start

1. **Python ≥ 3.13** — `python --version`
2. **aereo installed** — run `uv sync` from the repo root
3. **Earthdata login** (only for NASA sensors in example 04: VIIRS, Sentinel-3):
   ```bash
   # Option 1: Create a .netrc file
   echo "machine urs.earthdata.nasa.gov login YOUR_USER password YOUR_PASS" >> ~/.netrc
   chmod 600 ~/.netrc

   # Option 2: Environment variables
   export EARTHDATA_USERNAME=YOUR_USER
   export EARTHDATA_PASSWORD=YOUR_PASS
   ```
4. **Disk space**: ~500 MB–2 GB per sensor

---

## Quick Start: Pick an Example

The numbered examples demonstrate different features. Start with **01** and work upward.

| Example | Sensor | Plugins | Auth | ⏱ Est. Time | 💾 Disk | Recommended |
|---------|--------|---------|------|:-----------:|:-------:|:-----------:|
| [`01_minimal_goes.py`](extraction/01_minimal_goes.py) | GOES-19 ABI | aws-goes + satpy | None ✅ | ~3 min | ~200 MB | ⭐ **Start here** |
| [`02_goes_mosaic_plot.py`](extraction/02_goes_mosaic_plot.py) | GOES-19 ABI | aws-goes + satpy | None ✅ | ~3 min | ~200 MB | |
| [`03_sentinel2_msi.py`](extraction/03_sentinel2_msi.py) | Sentinel-2 MSI | planetary-computer + odc-stac | None ✅ | ~5 min | ~500 MB | |
| [`04_multi_constellation.py`](extraction/04_multi_constellation.py) | VIIRS + GOES + S3 OLCI | earthaccess + satpy / aws-goes + satpy | Earthdata 🔐 | ~10 min | ~1 GB | |
| [`05_conform_to_ml.py`](extraction/05_conform_to_ml.py) | Sentinel-2 MSI | planetary-computer + odc-stac | None ✅ | ~5 min | ~500 MB | |
| [`06_geotessera.py`](extraction/06_geotessera.py) | GeoTessera | search-tessera + extract-tessera | None ✅ | ~2 min | ~100 MB | |

### Running an Example

Directly with Python:

```bash
cd aer/examples/extraction
uv run python 01_minimal_goes.py
```

Or open in VS Code / Jupyter with `# %%` cell markers:

```bash
cd aer
uv run jupyter notebook examples/extraction/01_minimal_goes.py
```

Every example follows the same 4-step pattern:
1. **Search** — Find granules intersecting an AOI for a date range
2. **Prepare** — Generate grid cells and create extraction tasks
3. **Extract** — Download and process raw data into GeoTIFFs
4. **Output** — Files organized by `location/date/profile/collection/variable/resolution`

> 📖 New to AER? Read the [root README](../index.md) for the full quickstart and API overview.

---

## Directory Structure

```
examples/
├── extraction/           # Numbered extraction examples
│   ├── 01_minimal_goes.py
│   ├── 02_goes_mosaic_plot.py
│   ├── 03_sentinel2_msi.py
│   ├── 04_multi_constellation.py
│   ├── 05_conform_to_ml.py
│   └── 06_geotessera.py
├── grid/                 # Grid system and filtering demonstrations
├── data/                 # Shared sample AOIs (GeoJSON files)
│   ├── chocon.geojson
│   ├── buenos_aires.geojson
│   ├── cordoba.geojson
│   ├── bari.geojson
│   └── test_aoi.geojson
└── extract_*/            # Extracted output directories (auto-generated, not in git)
```

---

## Core Concepts

After running your first example, here are the key abstractions:

| Concept | What it does |
|---------|--------------|
| **`AerClient`** | Central orchestrator. Auto-discovers plugins, routes searches, delegates extraction. |
| **`AerProfile`** | Blueprint: which bands to extract, target resolution, plugin-specific params. |
| **`prepare_for_extraction`** | Groups results by profile and time, generates grid cells, chunks into tasks. |
| **`execute_tasks`** | Executes tasks through a configurable `ExecutionBackend` (sequential, process pool, or remote). |
| **`conform_to`** | When set to `(W, H)`, every cell in the batch is padded to the same `(width, height)` for fixed tensor shapes. |
| **EOIDS** | Output file structure: `loc-<cell>/date-<YYYYMMDD>/sat-<platform>/...tif` |

---

## Common `AerProfile` Errors and Fixes

The most common failures when running AER examples are incorrect `AerProfile` definitions. Here is a single reference for the pitfalls each example documents inline.

### GOES (examples 02, 04)

| Error | Cause | Fix |
|-------|-------|-----|
| Search returns empty or wrong satellite | Missing `search_params={"satellite": "GOES-19"}` | Add `search_params` to the profile |
| `ReaderNotAvailable` from satpy | Missing `extract_params["reader"]` | Add `extract_params={"reader": "abi_l1b", ...}` |

### Sentinel-2 (examples 03, 05)

| Error | Cause | Fix |
|-------|-------|-----|
| `PluginNotFoundError` | Using old plugin name `search_pc_sentinel2` | Use `search_planetary_computer` |
| Empty search results | Wrong collection name (`sentinel-2-l1c` vs `sentinel-2-l2a`) | Use `sentinel-2-l2a` |
| `odc-stac` cannot resolve bands | Bands declared in wrong place | Declare bands in `profile.collections` mapping; `extract_odc_stac` reads from there |

### VIIRS (example 04)

| Error | Cause | Fix |
|-------|-------|-----|
| `KeyError` for missing geolocation arrays | `VJ203IMG` (geolocation) omitted from `collections` | Always pair `VJ202IMG` with `VJ203IMG` even if no variables are extracted from it |
| Assets cannot be downloaded | Missing `downloader` | Set `downloader="aer.search_earthaccess.earthaccess_download_wrapper"` |
| `ReaderNotAvailable` from satpy | Missing `extract_params["reader"]` | Add `extract_params={"reader": "viirs_l1b", ...}` |

### Sentinel-3 OLCI (example 04)

| Error | Cause | Fix |
|-------|-------|-----|
| Assets cannot be downloaded | Missing `downloader` | Set `downloader="aer.search_earthaccess.earthaccess_download_wrapper"` |
| `ReaderNotAvailable` from satpy | Missing `extract_params["reader"]` | Add `extract_params={"reader": "olci_l1b", ...}` |

---

## ML-Ready `conform_to` Workflows (example 05)

`conform_to` forces every extracted tile to identical pixel dimensions, which is essential for PyTorch / TensorFlow pipelines.

### Deriving `conform_to` from a geographic patch size

```python
PATCH_KM = 2_560      # meters — must match target_grid_dist
RESOLUTION = 10       # Sentinel-2 10 m bands

conform_shape = (PATCH_KM // RESOLUTION, PATCH_KM // RESOLUTION)  # (256, 256)
```

Then set it on the profile:

```python
AerProfile(
    name="s2_ml",
    resolution=10,
    collections={"sentinel-2-l2a": ["B04", "B03", "B02", "B08"]},
    plugin_hints={"search": "search_planetary_computer", "extract": "extract_odc_stac"},
    conform_to=conform_shape,
    padding=16,
)
```

### How padding interacts with `conform_to`

- **`conform_to=(256, 256)`** defines the **valid** region width and height.
- **`padding=16`** adds 16 pixels on **each side**.
- **Total raster size** becomes `(256 + 2*16, 256 + 2*16) = (288, 288)`.
- The convention is **`(width, height)`**, matching rasterio's `(bands, height, width)` order.

### Stacking outputs into `(N, C, H, W)` tensors

```python
import numpy as np
import rasterio
from pathlib import Path

tifs = sorted(Path("/tmp/05_conform_to_ml_extraction").rglob("*.tif"))
arrays = [rasterio.open(tif).read() for tif in tifs]  # each is (C, H, W)
stack = np.stack(arrays)  # (N, C, H, W)
assert stack.shape[-2:] == conform_shape
```

See [`05_conform_to_ml.py`](extraction/05_conform_to_ml.py) for the full runnable example including montage visualization.

---

## Grid Filtering (`grid/`)

When preparing extraction tasks, grid cells can be filtered based on their relationship to the satellite swath footprint. This prevents extracting near-empty cells.

### Three Filter Modes

| Mode | Parameter | Behavior | Use Case |
|------|-----------|----------|----------|
| **Intersection** | `grid_filter_mode='intersection'` (default) | Cell touches asset geometry at any point | Maximize coverage |
| **Within** | `grid_filter_mode='within'` | Cell is fully inside asset geometry | Only fully valid cells |
| **Coverage** | `grid_filter_mode='coverage'` + `min_coverage=0.5` | Cell has ≥X% area inside geometry | Balanced approach |

### Visual Comparison

Using a real VIIRS granule over Buenos Aires (13 grid cells total):

![Grid Filter Modes Comparison](../assets/grid_filter_modes_comparison.png)

- **Green cells**: Selected for extraction
- **Red cells**: Discarded by the filter
- **Light blue**: Asset geometry (actual satellite swath footprint)
- **Black outline**: Area of Interest (AOI)

**Coverage percentages per cell:**

![Grid Filter Coverage Detail](../assets/grid_filter_coverage_detail.png)

| Filter Mode | Cells Selected | Cells Discarded |
|-------------|:--------------:|:---------------:|
| `intersection` | 8 | 5 |
| `within` | 3 | 10 |
| `coverage >= 50%` | 5 | 8 |

### Usage

```python
from aereo.interfaces import GridConfig

grid = GridConfig(
    target_grid_dist=50_000,
    grid_filter_mode="coverage",
    min_coverage=0.5,
)

client.prepare_for_extraction(
    search_results=results,
    grid_config=grid,
    profiles=profiles,
    uri="output/extraction",
    cells_per_chunk=10,
)
```

See [grid/grid_filter_modes_demo.ipynb](grid/grid_filter_modes_demo.ipynb) for the full demonstration.

---

## Sample AOIs

All sample AOIs are in the `data/` directory and shared across examples:

| File | Region | Coordinates (approx) |
|------|--------|---------------------|
| `data/chocon.geojson` | Chocon, Argentina | -69.8,-40.0 to -68.2,-39.1 |
| `data/buenos_aires.geojson` | Buenos Aires province, Argentina | -63.5,-41 to -57,-34 |
| `data/cordoba.geojson` | Cordoba province, Argentina | -65.5,-33 to -62,-29 |
| `data/bari.geojson` | Bari, Italy | 16.5,40.8 to 17.5,41.2 |
| `data/test_aoi.geojson` | Small test polygon | Minimal bounding box |

---

## EOIDS Output Structure

Extracted data follows the [Earth Observation Imaging Data Structure](../eoids.md) convention:

```
extract_buenos_aires_viirs/
├── loc-15D21L/
│   └── date-20260401/
│       └── profile-viirs_i1/
│           └── collection-VJ202IMG/
│               └── variable-I04/
│                   └── loc-15D21L_start-..._profile-viirs_i1_collection-VJ202IMG_variable-I04_res-400m.tif
└── ...
```

These directories are generated by running extraction examples and are **not** tracked in git.

---

## Notes

- **Grid cell size**: Default is 256 km (`target_grid_dist=256000`). Adjust based on sensor resolution and AOI size.
- **Natural shapes**: By default, each cell's output matches its natural UTM footprint, so adjacent cells tile edge-to-edge with no gaps.
- **`conform_to`**: Set to `(W, H)` when you need fixed tensor shapes (e.g. ML training). Every cell is padded to the same `(width, height)` with `NaN` fill.
- **Padding**: Extra border pixels added on each side (e.g. `padding=2`). Useful for CNN receptive fields or context windows — not a gap-fix, since natural shapes already tile seamlessly.
- **Resampling**: Default `nearest`. Alternatives: `bilinear`, `native`.
- **Workers**: `max_batch_workers=2` for parallel extraction. Set to `None` for sequential (safer for memory).
