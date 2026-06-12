---
title: Advanced Pipeline Options
---

# Advanced Pipeline Options

This page covers the full API for `AereoClient.search()`, `prepare_for_extraction()`, and `execute_tasks()` — parameters, backends, edge cases, and production patterns.

For a gentle introduction, see [Your First Pipeline](first-pipeline.md).

---

## Search

Find satellite granules that match your time range, area of interest, and sensor profile. AEREO fans the query out to registered **search plugins** in parallel and returns a single validated GeoDataFrame.

### Minimal example

```python
from datetime import datetime, timezone
from shapely.geometry import box
from aereo.client import AereoClient
from aereo.interfaces import GridConfig
from aereo.interfaces import AereoProfile

aoi = box(-69.76, -39.98, -68.24, -39.05)

profiles = [
    AereoProfile(
        name="goes_c02",
        resolution=500,
        collections={"ABI-L1b-RadF": ["C02"]},
        plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
        search_params={"satellite": "GOES-19"},
    )
]

client = AereoClient(
    profiles=profiles,
    aoi=aoi,
)

results = client.search(
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 9, tzinfo=timezone.utc),
)
print(f"Found {len(results)} assets")
print(results[["id", "collection", "start_time"]].head())
```

### Key parameters

| Parameter | What it does |
|-----------|--------------|
| `profiles` | **Required.** List of `AereoProfile` objects. Each profile carries its own `collections`, `search_params`, and `plugin_hints`. The client groups profiles by target plugin to avoid redundant API calls. |
| `intersects` | Spatial filter. Accepts a Shapely `BaseGeometry`, a GeoJSON `dict`, or a path to a GeoJSON file (``.geojson``/``.json``). |
| `start_datetime` / `end_datetime` | UTC `datetime` objects for temporal filtering. |
| `search_params` | Meta-level dict forwarded to search plugins. Supports **per-collection overrides** using collection names as top-level keys (case-insensitive). Profile-level `search_params` always wins over batch-level. |
| `failure_mode` | `BEST_EFFORT` (default) logs failures and continues. `STRICT` raises on any plugin failure. |

### Common pattern: searching multiple collections

Pass several profiles at once. AEREO will dispatch them to the right plugins automatically.

```python
from datetime import datetime, timezone

profiles = [
    AereoProfile(
        name="goes_c02",
        resolution=500,
        collections={"ABI-L1b-RadF": ["C02"]},
        plugin_hints={"search": "search_aws_goes"},
        search_params={"satellite": "GOES-19"},
    ),
    AereoProfile(
        name="s2_ndvi",
        resolution=10,
        collections={"Sentinel-2-L2A": ["B04", "B08"]},
    ),
]

client = AereoClient(
    profiles=profiles,
    aoi=aoi,
)

results = client.search(
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 9, tzinfo=timezone.utc),
)
```

### Return value inspection

`search()` returns a `GeoDataFrame[AssetSchema]` with these columns:

| Column | Description |
|--------|-------------|
| `id` | Unique granule identifier |
| `collection` | Collection this asset belongs to |
| `geometry` | Satellite swath footprint (may be `None`) |
| `start_time` / `end_time` | Acquisition window |
| `href` | Download URL or data reference |

### Gotcha: `BEST_EFFORT` vs `STRICT`

With `BEST_EFFORT` (the default), a failing plugin is logged and skipped — you may get a partially filled result or an empty GeoDataFrame. With `STRICT`, any plugin failure raises `RuntimeError` immediately. Use `STRICT` in CI or when you need guarantees; use `BEST_EFFORT` in exploratory notebooks or multi-sensor queries where one source being down is acceptable.

---

## Prepare

Turn search results into a list of `ExtractionTask` objects. AEREO builds a grid over your AOI, groups assets by profile and start time, filters grid cells by swath coverage, and chunks everything into parallelizable units.

### Minimal example

```python
client = AereoClient(
    profiles=profiles,
    aoi=aoi,
    grid_config=GridConfig(target_grid_dist=256_000, target_grid_overlap=False),
    cells_per_task=10,
)

tasks = client.prepare_for_extraction(
    search_results=results,
    output_uri="/tmp/goes_extraction",
)
print(f"Prepared {len(tasks)} extraction tasks")
print(f"Task 0 covers {len(tasks[0].grid_cells)} cells")
```

### Key parameters

| Parameter | What it does |
|-----------|--------------|
| `search_results` | **Required.** Output from `client.search()`. |
| `profiles` / `resolution` | **At least one is required.** If `profiles` is omitted, a default profile named `"default"` is created with the given `resolution`. |
| `target_aoi` | Clipping geometry. If `None`, the extractor uses the union of all asset geometries. |
| `output_uri` | Base output directory or URI prefix for extracted artifacts. |
| `prepare_params` | Forwarded to the extractor. Common keys: `cells_per_task` (default 50), `grid_filter_mode` (`"intersection"`, `"within"`, `"coverage"`), `min_coverage` (float 0.0–1.0). |
| `target_grid_dist` | Override grid cell size in metres (e.g. `256000` for 256 km cells). |
| `target_grid_overlap` | Override whether grid cells are allowed to overlap. |

### Common pattern: preparing multiple profiles at once

Pass the same `profiles` list you used in `search()`. `prepare_for_extraction()` uses `profile.resolution`, `profile.extract_params`, and `profile.conform_to` to build tasks.

```python
# profiles and grid_config were used for both search() and prepare_for_extraction()
client = AereoClient(
    profiles=profiles,
    grid_config=GridConfig(target_grid_dist=128_000),
)

tasks = client.prepare_for_extraction(
    results,
    output_uri="/tmp/output",
)
```

### The two outputs

`prepare_for_extraction()` returns a `Sequence[ExtractionTask]`. Each task contains:

| Attribute | Description |
|-----------|-------------|
| `assets` | GeoDataFrame of granules this task will process |
| `patches` | Spatial patches this task covers |
| `job` | Parent `ExtractionJob` owning extraction configuration |
| `extract` | Declarative configuration of extraction stages (from `job.extract`) |
| `output_uri` | Destination path or URI for artifacts (from `job.output_uri`) |
| `grid_config` | Tiling specification for this run (from `job.grid_config`) |
| `patch_config` | ML physical patch dimensions (from `job.patch_config`) |
| `aoi` | Clipping geometry used during preparation |
| `task_context` | Metadata such as `chunk_id`, `total_chunks`, `start_time` |

### Gotcha: `target_grid_dist` is cell size, `resolution` is pixel size

`target_grid_dist` controls how large each grid **cell** is in metres (e.g. `256000` = 256 km squares). `profile.resolution` controls the output **pixel** size in metres (e.g. `500` = 500 m pixels). A 256 km cell at 500 m resolution is roughly a 512 × 512 pixel tile. Mixing these up is the most common source of "why is my grid so tiny?" confusion.

---

## Extract

Run the extraction. Each `ExtractionTask` is handed to the registered **Extractor** plugin, which downloads granules, resamples to the target grid, and writes GeoTIFFs in EOIDS format.

### Minimal example

```python
from aereo.backends import LocalProcessBackend

backend = LocalProcessBackend(max_workers=4)
artifacts = client.execute_tasks(tasks, backend=backend)
print(f"Extracted {len(artifacts)} artifacts")
print(artifacts[["id", "grid_cell", "uri"]].head())
```

### Key parameters

| Parameter | What it does |
|-----------|--------------|
| `tasks` | **Required.** Output from `prepare_for_extraction()`. |
| `backend` | `ExecutionBackend` implementation. Defaults to `LocalProcessBackend()` (sequential). Use `LocalProcessBackend(max_workers=4)` for process parallelism, `ThreadBackend(max_workers=8)` for thread parallelism, or `LambdaBackend(...)` for remote execution. |
| `failure_mode` | `STRICT` (default) raises on any failure. `BEST_EFFORT` returns an empty GeoDataFrame on failure. |

### Return value: `ArtifactSchema` GeoDataFrame

`execute_tasks()` returns a `GeoDataFrame[ArtifactSchema]` with these key columns:

| Column | Description |
|--------|-------------|
| `id` | Unique artifact identifier |
| `source_ids` | Comma-separated source granule IDs |
| `uri` | Absolute path to the extracted GeoTIFF |
| `geometry` | Spatial footprint of the extracted tile |
| `grid_cell` | Cell ID (e.g. `17D20L`) |
| `grid_dist` | Cell size in metres |
| `cell_utm_crs` | UTM EPSG code |

### Common pattern: extracting to EOIDS and mosaicking

Artifacts are written to disk following the **EOIDS** convention. After extraction, you can mosaic tiles:

```python
from aereo.eoids import mosaic_eoids_tiles

mosaic, transform, crs = mosaic_eoids_tiles("/tmp/goes_extraction", target_crs="EPSG:4326")
```

See [Output Formats](output-formats.md) for the full directory layout and mosaic options.

### Gotcha: plugin-specific errors surface here

If a granule is missing, a band is unsupported, or a download times out, the error usually appears during `execute_tasks()`, not `search()` or `prepare_for_extraction()`. Use `failure_mode=BEST_EFFORT` to skip bad granules and keep the rest, or wrap the call in your own retry logic. The `LocalProcessBackend` uses `ProcessPoolExecutor` — exceptions in worker processes are captured and re-raised (or logged) by the client.

> [!TIP]
> **Extraction fails with `ReaderNotAvailable`?** Satpy-based extractors need a `reader` in `extract_params`:
> | Sensor | Reader |
> |--------|--------|
> | GOES ABI | `abi_l1b` |
> | VIIRS | `viirs_l1b` |
> | Sentinel-3 OLCI | `olci_l1b` |
>
> ```python
> AereoProfile(
>     ...,
>     extract_params={"reader": "abi_l1b", "calibration": "reflectance"},
> )
> ```

> [!TIP]
> **NASA Earthdata assets fail with HTTP 401?** NASA Earthdata URLs are behind URS authentication. Add the Earthdata downloader to your profile:
> ```python
> AereoProfile(
>     ...,
>     downloader="aereo.search_earthaccess.earthaccess_download_wrapper",
> )
> ```

> [!TIP]
> **Out of memory during extraction?** Large mosaics or high-resolution extractions can exhaust RAM. Try:
> - Reduce `cells_per_task` (e.g., `1` instead of `50`).
> - Reduce `max_workers` (e.g., `1` instead of `8`).
> - Use a smaller AOI or coarser `target_grid_dist`.
> - Process one profile at a time instead of multiple sensors in parallel.
