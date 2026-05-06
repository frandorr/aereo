# AER Examples

Jupyter notebooks demonstrating the AER (Asset Extraction and Retrieval) framework for satellite data processing.

---

## Before You Start

1. **Python ≥ 3.13** — `python --version`
2. **aer installed** — run `uv sync` from the repo root
3. **Earthdata login** (only for NASA sensors: MODIS, VIIRS, Sentinel-3):
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

## Quick Start: Pick a Notebook

| Notebook | Sensor | Auth | ⏱ Est. Time | 💾 Disk | Recommended |
|----------|--------|:----:|:-----------:|:-------:|:-----------:|
| [goes_abi_extraction.ipynb](extraction/goes_abi_extraction.ipynb) | GOES-19 ABI | None ✅ | ~3 min | ~200 MB | ⭐ **Start here** |
| [sentinel2_msi_extraction.ipynb](extraction/sentinel2_msi_extraction.ipynb) | Sentinel-2 MSI | None ✅ | ~5 min | ~500 MB | |
| [modis_terra_extraction.ipynb](extraction/modis_terra_extraction.ipynb) | MODIS Terra | Earthdata 🔐 | ~5 min | ~800 MB | |
| [viirs_extraction.ipynb](extraction/viirs_extraction.ipynb) | VIIRS (NOAA-21) | Earthdata 🔐 | ~8 min | ~1 GB | |
| [sentinel3_olci_extraction.ipynb](extraction/sentinel3_olci_extraction.ipynb) | Sentinel-3 OLCI | Earthdata 🔐 | ~10 min | ~2 GB | |

### Running a Notebook

```bash
cd aer
uv run jupyter notebook examples/
```

Or convert to a script and run directly:

```bash
cd aer/examples/extraction
uv run jupyter nbconvert --to script goes_abi_extraction.ipynb
uv run python goes_abi_extraction.py
```

Every notebook follows the same 4-step pattern:
1. **Search** — Find granules intersecting an AOI for a date range
2. **Prepare** — Generate grid cells and create extraction tasks
3. **Extract** — Download and process raw data into GeoTIFFs
4. **Output** — Files organized by `location/date/satellite/product/band/resolution`

> 📖 New to AER? Read the [root README](../README.md) for the full quickstart and API overview.

---

## Directory Structure

```
examples/
├── extraction/           # Extraction notebooks (one per sensor)
├── grid/                 # Grid system and filtering demonstrations
├── visualization/        # Multi-sensor visualization examples
├── data/                 # Shared sample AOIs (GeoJSON files)
│   ├── buenos_aires.geojson
│   ├── cordoba.geojson
│   ├── bari.geojson
│   └── test_aoi.geojson
└── extract_*/            # Extracted output directories (auto-generated, not in git)
```

---

## Core Concepts

After running your first notebook, here are the key abstractions:

| Concept | What it does |
|---------|--------------|
| **`AerClient`** | Central orchestrator. Auto-discovers plugins, routes searches, delegates extraction. |
| **`ExtractionProfile`** | Blueprint: which bands to extract, target resolution, plugin-specific params. |
| **`prepare_for_extraction`** | Groups results by profile and time, generates grid cells, chunks into tasks. |
| **`extract_batches`** | Executes tasks — sequential or parallel via `ProcessPoolExecutor`. |
| **EOIDS** | Output file structure: `loc-<cell>/date-<YYYYMMDD>/sat-<platform>/...tif` |

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

![Grid Filter Modes Comparison](grid/grid_filter_modes_comparison.png)

- **Green cells**: Selected for extraction
- **Red cells**: Discarded by the filter
- **Light blue**: Asset geometry (actual satellite swath footprint)
- **Black outline**: Area of Interest (AOI)

**Coverage percentages per cell:**

![Grid Filter Coverage Detail](grid/grid_filter_coverage_detail.png)

| Filter Mode | Cells Selected | Cells Discarded |
|-------------|:--------------:|:---------------:|
| `intersection` | 8 | 5 |
| `within` | 3 | 10 |
| `coverage >= 50%` | 5 | 8 |

### Usage

```python
client.prepare_for_extraction(
    search_results=results,
    profiles=profiles,
    uri="output/extraction",
    prepare_params={
        "grid_filter_mode": "coverage",   # or "intersection", "within"
        "min_coverage": 0.5,               # 0.0 to 1.0, only for "coverage" mode
        "cells_per_chunk": 10,
    },
)
```

See [grid/grid_filter_modes_demo.ipynb](grid/grid_filter_modes_demo.ipynb) for the full demonstration.

---

## Visualization Examples (`visualization/`)

| Notebook | Description |
|----------|-------------|
| [multi_constellation_visualization.ipynb](visualization/multi_constellation_visualization.ipynb) | Compare multiple sensors (GOES, MODIS, Sentinel-2, Sentinel-3, VIIRS) in a single view |

**Output example — Same grid cell viewed by four sensors:**

![Single Cell Comparison](visualization/single_cell_comparison.png)

---

## Sample AOIs

All sample AOIs are in the `data/` directory and shared across notebooks:

| File | Region | Coordinates (approx) |
|------|--------|---------------------|
| `data/buenos_aires.geojson` | Buenos Aires province, Argentina | -63.5,-41 to -57,-34 |
| `data/cordoba.geojson` | Cordoba province, Argentina | -65.5,-33 to -62,-29 |
| `data/bari.geojson` | Bari, Italy | 16.5,40.8 to 17.5,41.2 |
| `data/test_aoi.geojson` | Small test polygon | Minimal bounding box |

---

## EOIDS Output Structure

Extracted data follows the [Earth Observation Imaging Data Structure](../docs/eoids.md) convention:

```
extract_buenos_aires_viirs/
├── loc-15D21L/
│   └── date-20260401/
│       └── sat-NOAA21/
│           └── loc-15D21L_start-..._band-I04_res-400m.tif
└── ...
```

These directories are generated by running extraction notebooks and are **not** tracked in git.

---

## Notes

- **Grid cell size**: Default is 256 km (`target_grid_dist=256000`). Adjust based on sensor resolution and AOI size.
- **Padding**: Default 2 pixels. Increases extracted area slightly to avoid edge artifacts.
- **Resampling**: Default `nearest`. Alternatives: `bilinear`, `native`.
- **Workers**: `max_batch_workers=2` for parallel extraction. Set to `None` for sequential (safer for memory).
