# AEREO in 5 minutes

AEREO turns satellite catalog data into analysis-ready GeoTIFFs on the Major TOM
grid. It is built around plain Python functions, not classes.

---

## The mental model: three steps

Every AEREO pipeline follows the same shape:

![Search → Prepare → Execute](assets/pipeline-walkthrough/01-step1-search-and-task-preparation.png)

1. **Search** — find assets in a catalog.
2. **Prepare** — turn those assets into extraction tasks on a shared grid.
3. **Execute** — run each task through read → write (per patch).

---

## Core concepts

| Concept | What it is | Why it matters |
|---|---|---|
| `ExtractionJob` | A validated config bundle: grid, patch size, output URI, and stage pipeline. | One object carries everything except the search and task-builder choices. |
| Search function | A plain function like `search_stac`. | You pass it to `job.search(...)` with keyword arguments. No class boilerplate. |
| Task builder function | A plain function like `build_grouped_tasks`. | Groups search results into `ExtractionTask` objects by time and native CRS. |
| `ExtractionTask` | One unit of work: assets + grid patches + stage pipeline. | The executor runs these in parallel. |
| Stage functions | `read_odc_stac`, `reproject_odc`, `write_geotiff`, `ndvi`, etc. | Passed directly to `ExtractionJob(read=..., write=...)`. Pure functions, composable, easy to test. |
| `LocalExecutor` | Runs tasks locally with threads or processes. | Swap for Lambda later without changing the pipeline. |

---

## The 10-line experience

```python
from datetime import datetime, timezone
from aereo.builtins import build_grouped_tasks, search_stac
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

# Load the job (grid + patch + extract stages)
job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

# Search → Prepare tasks → Execute
assets = job.search(
    search_stac,
    stac_api_url="https://earth-search.aws.element84.com/v1",
    collections={"sentinel-2-l2a": ["red", "nir"]},
    intersects="examples/config/aoi/chocon.geojson",
    start_datetime=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end_datetime=datetime(2024, 1, 10, tzinfo=timezone.utc),
)
tasks = job.build_tasks(assets, build_grouped_tasks, cells_per_task=5)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))
```

No classes to subclass. No global state. Hydra configs are optional.

---

## What you can do

- Extract Sentinel-2, VIIRS, GOES-19, and more by swapping search/read functions.
- Compose processing steps (`ndvi`, `qa_mask`, `select_bands`, `composite`) as `read` and `write` callables on the `ExtractionJob` (per-patch reprojection and pre/post-processing are deferred to the reader/writer implementations).
- Run the same pipeline from Python, CLI, or AWS Lambda using the same YAML configs.
- Output standard EOIDS GeoTIFFs on the Major TOM grid — ready for ML and mosaics.

---

## Why AEREO?

| Problem | How AEREO solves it |
|---|---|
| Every catalog has a different API | One `job.search(...)` call with swappable search functions. |
| Tiles do not line up across sensors | Built-in Major TOM grid + UTM patch geoboxes. |
| Reprojection boilerplate | Readers/writers can call `reproject_odc` (or any reprojector) as needed. |
| Mixed-CRS scenes fail | `build_grouped_tasks` groups assets by native CRS. |
| Notebook → production is hard | Same config package runs in Python, CLI, and Lambda. |
| Plugin frameworks force inheritance | AEREO plugins are `@validate_call` functions + entry points. |

---

## The most common mistake

Confusing **cell size** with **pixel size**:

- `grid_dist` = size of the grid cell in metres (e.g. `10_000` for 10 km).
- `patch_config.resolution` = size of each output pixel in metres (e.g. `10.0` for 10 m).

A 10 km cell at 10 m resolution is a 1000 × 1000 pixel tile. Swapping them is the
fastest way to get nonsense outputs.

---

## Suggested learning path

1. Run `examples/quickstart_pure_python.py` with `DRY_RUN=true` to see a job built without YAML.
2. Run `examples/config/run_job.py` with `DRY_RUN=true` to see the Hydra config-package pattern.
3. Open `examples/step_by_step_raw.ipynb` to see each function called in isolation.
4. Try `aereo action=plugins` and `aereo action=plugin_params plugin_name=search_stac`.
5. Read [Build Your First Plugin](plugins/build-first-plugin.md) and write a 20-line function plugin.

---

## Next steps

- [Your First Pipeline](first-pipeline.md) — a guided first extraction.
- [Examples Gallery](examples/index.md) — runnable notebooks for every sensor.
- [Pipeline Architecture](concepts/pipeline-architecture.md) — the full stage model.
- [Working with Grids](concepts/grids.md) — how the Major TOM grid works.
