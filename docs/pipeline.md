# Running the Pipeline

AER's entire user experience is built around three `AerClient` methods: `search()`, `prepare_for_extraction()`, and `execute_tasks()`. This page shows you how to use each one with practical examples, common patterns, and the gotchas that matter in production.

For deep technical internals — UML diagrams, exact schema tables, and sequence diagrams — see [Pipeline Architecture](pipeline-architecture.md).

---

## Search

Find satellite granules that match your time range, area of interest, and sensor profile. AER fans the query out to registered **search plugins** in parallel and returns a single validated GeoDataFrame.

### Minimal example

```python
from datetime import datetime, timezone
from shapely.geometry import box
from aer.client import AerClient
from aer.grid import GridConfig
from aer.interfaces import AerProfile

aoi = box(-69.76, -39.98, -68.24, -39.05)

profiles = [
    AerProfile(
        name="goes_c02",
        resolution=500,
        collections={"ABI-L1b-RadF": ["C02"]},
        plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
        search_params={"satellite": "GOES-19"},
    )
]

client = AerClient(
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
| `profiles` | **Required.** List of `AerProfile` objects. Each profile carries its own `collections`, `search_params`, and `plugin_hints`. The client groups profiles by target plugin to avoid redundant API calls. |
| `intersects` | Spatial filter. Accepts a Shapely `BaseGeometry` or a GeoJSON `dict`. |
| `start_datetime` / `end_datetime` | UTC `datetime` objects for temporal filtering. |
| `search_params` | Meta-level dict forwarded to search plugins. Supports **per-collection overrides** using collection names as top-level keys (case-insensitive). Profile-level `search_params` always wins over batch-level. |
| `failure_mode` | `BEST_EFFORT` (default) logs failures and continues. `STRICT` raises on any plugin failure. |

### Common pattern: searching multiple collections

Pass several profiles at once. AER will dispatch them to the right plugins automatically.

```python
from datetime import datetime, timezone

profiles = [
    AerProfile(
        name="goes_c02",
        resolution=500,
        collections={"ABI-L1b-RadF": ["C02"]},
        plugin_hints={"search": "search_aws_goes"},
        search_params={"satellite": "GOES-19"},
    ),
    AerProfile(
        name="s2_ndvi",
        resolution=10,
        collections={"Sentinel-2-L2A": ["B04", "B08"]},
    ),
]

client = AerClient(
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

Turn search results into a list of `ExtractionTask` objects. AER builds a grid over your AOI, groups assets by profile and start time, filters grid cells by swath coverage, and chunks everything into parallelizable units.

### Minimal example

```python
client = AerClient(
    profiles=profiles,
    aoi=aoi,
    grid_config=GridConfig(target_grid_dist=256_000, target_grid_overlap=False),
    cells_per_task=10,
)

tasks = client.prepare_for_extraction(
    search_results=results,
    uri="/tmp/goes_extraction",
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
| `uri` | Base output directory for extracted artifacts. |
| `prepare_params` | Forwarded to the extractor. Common keys: `cells_per_task` (default 50), `grid_filter_mode` (`"intersection"`, `"within"`, `"coverage"`), `min_coverage` (float 0.0–1.0). |
| `target_grid_dist` | Override grid cell size in metres (e.g. `256000` for 256 km cells). |
| `target_grid_overlap` | Override whether grid cells are allowed to overlap. |

### Common pattern: preparing multiple profiles at once

Pass the same `profiles` list you used in `search()`. `prepare_for_extraction()` uses `profile.resolution`, `profile.extract_params`, and `profile.conform_to` to build tasks.

```python
# profiles and grid_config were used for both search() and prepare_for_extraction()
client = AerClient(
    profiles=profiles,
    grid_config=GridConfig(target_grid_dist=128_000),
)

tasks = client.prepare_for_extraction(
    results,
    uri="/tmp/output",
)
```

### The two outputs

`prepare_for_extraction()` returns a `Sequence[ExtractionTask]`. Each task contains:

| Attribute | Description |
|-----------|-------------|
| `assets` | GeoDataFrame of granules this task will process |
| `profile` | The `AerProfile` with bands, resolution, and params |
| `grid_cells` | Spatial cells this task covers |
| `uri` | Destination path for artifacts |
| `task_context` | Metadata such as `chunk_id`, `total_chunks`, `start_time`. Contains `conform_to_shape` when the profile enables fixed-shape batching. |

### Gotcha: `target_grid_dist` is cell size, `resolution` is pixel size

`target_grid_dist` controls how large each grid **cell** is in metres (e.g. `256000` = 256 km squares). `profile.resolution` controls the output **pixel** size in metres (e.g. `500` = 500 m pixels). A 256 km cell at 500 m resolution is roughly a 512 × 512 pixel tile. Mixing these up is the most common source of "why is my grid so tiny?" confusion.

---

## Extract

Run the extraction. Each `ExtractionTask` is handed to the registered **Extractor** plugin, which downloads granules, resamples to the target grid, and writes GeoTIFFs in EOIDS format.

### Minimal example

```python
from aer.execution import LocalProcessBackend

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
| `failure_mode` | **Defaults to `STRICT`** (unlike `search()`). `BEST_EFFORT` logs and continues. |

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
from aer.eoids import mosaic_eoids_tiles

mosaic, transform, crs = mosaic_eoids_tiles("/tmp/goes_extraction", target_crs="EPSG:4326")
```

See [EOIDS](eoids.md) for the full directory layout and mosaic options.

### Gotcha: plugin-specific errors surface here

If a granule is missing, a band is unsupported, or a download times out, the error usually appears during `execute_tasks()`, not `search()` or `prepare_for_extraction()`. Use `failure_mode=BEST_EFFORT` to skip bad granules and keep the rest, or wrap the call in your own retry logic. The `LocalProcessBackend` uses `ProcessPoolExecutor` — exceptions in worker processes are captured and re-raised (or logged) by the client.
