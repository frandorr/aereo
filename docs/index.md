<p align="center">
    <img src="banner.svg" alt="AEREO logo" style="max-width: 300px; width: 100%;">
</p>

---

Satellite data lives in a dozen different catalogs, each with its own API,
authentication, and file format. **AEREO** unifies them into a single pipeline:
**search** across catalogs, **prepare** extraction tasks on a shared grid, and
**execute** them through the executor of your choice — from a local notebook to
AWS Lambda.

<div class="grid cards" markdown>

-   ## AEREO in 5 minutes

    ---

    Learn the core concepts, what you can build, and why AEREO exists.

    [:octicons-arrow-right-24: Read Now](five-minutes.md)

-   ## Run your first pipeline

    ---

    Open the Sentinel-2 notebook and get a GeoTIFF in minutes.

    [:octicons-arrow-right-24: Get Started](first-pipeline.md)

-   ## Browse examples

    ---

    Sentinel-2, VIIRS, Sentinel-3, Tessera, GOES-19, and NDVI processing.

    [:octicons-arrow-right-24: Examples](examples/index.md)

-   ## Run from Python or CLI

    ---

    Use Hydra config packages with `ExtractionJob` and the `aereo` CLI.

    [:octicons-arrow-right-24: Run Aereo](run/index.md)

-   ## Build a plugin

    ---

    Add a new search provider, reader, or writer. AEREO plugins are plain
    Python functions registered via entry points.

    [:octicons-arrow-right-24: Learn How](plugins/plugin-overview.md)

-   ## API Reference

    ---

    Explore the complete API for power users and plugin developers.

    [:octicons-arrow-right-24: View API](api/pipeline.md)

</div>

---

## 10-line example

```python
from aereo.builtins import build_grouped_tasks, search_stac
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

# Load a Hydra config package (grid + patch + extract)
job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

# 1. Search   2. Prepare tasks   3. Execute
results = job.search(search_stac, stac_api_url="https://earth-search.aws.element84.com/v1")
tasks = job.build_tasks(results, build_grouped_tasks)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))
```

Open `job.output_uri` — you have GeoTIFFs on the Major TOM grid.

---

## How AEREO works

```text
┌─────────┐     ┌──────────────┐     ┌────────────────────┐     ┌───────────┐
│  Search │ ──▶ │ Prepare tasks│ ──▶ │ Execute on executor│ ──▶ │  EOIDS    │
│ provider│     │ Grid + Patch │     │ Local / Lambda     │     │ GeoTIFFs  │
└─────────┘     └──────────────┘     └────────────────────┘     └───────────┘
```

1. **Search** — a search function queries a catalog and returns a validated
   `GeoDataFrame[AssetSchema]`.
2. **Prepare** — AEREO builds grid cells over your AOI, groups assets by time,
   and chunks them into `ExtractionTask` objects.
3. **Execute** — an executor runs each task through the stage pipeline
   configured in `ExtractConfig`:
   `read function → preprocess functions → reproject function → postprocess functions → write function`.

All of this is configurable through Hydra YAML files or plain Python objects.

---

Apache License 2.0
