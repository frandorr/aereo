# aereo 🪐

[![PyPI](https://img.shields.io/pypi/v/aereo.svg)](https://pypi.org/project/aereo)
[![PyPI Downloads](https://img.shields.io/pypi/dm/aereo.svg)](https://pypi.org/project/aereo)
[![Python Versions](https://img.shields.io/pypi/pyversions/aereo.svg)](https://pypi.org/project/aereo)
[![CI](https://github.com/frandorr/aereo/actions/workflows/ci.yml/badge.svg)](https://github.com/frandorr/aereo/actions/workflows/ci.yml)
[![GitHub Issues](https://img.shields.io/github/issues/frandorr/aereo.svg)](https://github.com/frandorr/aereo/issues)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/frandorr/aereo/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://frandorr.github.io/aereo)

> Plugin-based satellite data extraction — from search to analysis-ready Major TOM grid in minutes.

---

Satellite data lives in a dozen different catalogs, each with its own API,
authentication, and file format. **AEREO** unifies them into a single pipeline:
**search** across catalogs, **prepare** extraction tasks on a shared grid, and
**execute** them through the executor of your choice.

AEREO is built around plain Python functions, not classes. Search providers,
readers, processors, reprojectors, and writers are all functions that you
compose into an `ExtractionJob`.

## Install

Pick your sensor and copy-paste:

```bash
# Sentinel-2 (Planetary Computer)
pip install aereo aereo-search-planetary-computer

# MODIS / VIIRS / Sentinel-3 (NASA Earthdata)
pip install aereo aereo-search-earthaccess

# GOES ABI (public S3, no auth)
pip install aereo aereo-search-aws-goes aereo-read-satpy aereo-reproject-satpy
```

> Install the core framework with `pip install aereo`. Search and I/O plugins
> are separate packages (e.g. `aereo-search-aws-goes`, `aereo-read-satpy`).

---

## 10-line example

```python
from datetime import datetime, timezone
from aereo.builtins import search_stac, build_grouped_tasks
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

# 1. Load the job (grid + patch + extract stages)
job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

# 2. Search   3. Prepare tasks   4. Execute
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

Open `job.output_uri` — you have GeoTIFFs on the Major TOM grid.

---

## Why AEREO?

| Problem | How AEREO solves it |
|---|---|
| Every catalog has a different API | One `job.search(...)` call with swappable search functions. |
| Tiles do not line up across sensors | Built-in Major TOM grid + UTM patch geoboxes. |
| Reprojection boilerplate | Readers/writers can call `reproject_odc` (or any reprojector) as needed. |
| Mixed-CRS scenes fail | `build_grouped_tasks` groups assets by native CRS. |
| Notebook → production is hard | Same config package runs in Python, CLI, and AWS Lambda. |
| Plugin frameworks force inheritance | AEREO plugins are `@validate_call` functions + entry points. |

---

## Core concepts

1. **`ExtractionJob`** — a validated bundle of grid size, output URI, and reader/writer callables.
2. **Search function** — e.g. `search_stac`. Pass it to `job.search(...)` with kwargs.
3. **Task builder function** — e.g. `build_grouped_tasks`. Groups assets into `ExtractionTask` objects.
4. **`ExtractionTask`** — one unit of work: assets + grid patches + stage pipeline.
5. **Stage functions** — `read_odc_stac`, `reproject_odc`, `ndvi`, `write_geotiff`, etc. Passed directly to `ExtractionJob(read=..., write=...)`.
6. **`LocalExecutor`** — runs tasks locally. Swap for Lambda later without changing the pipeline.

---

## Docs & Examples

- [AEREO in 5 Minutes](https://frandorr.github.io/aereo/five-minutes/) — concepts, wins, and first steps
- [Your First Pipeline](https://frandorr.github.io/aereo/first-pipeline/) — first extraction in 5 minutes
- [Examples](https://frandorr.github.io/aereo/examples/) — Sentinel-2, VIIRS, Sentinel-3, Tessera, GOES-19
- [Run with CLI](https://frandorr.github.io/aereo/run/run-with-cli/) — zero-code `aereo action=run`
- [Build a Plugin](https://frandorr.github.io/aereo/plugins/build-first-plugin/) — extend AEREO with a function

---

Apache License 2.0
