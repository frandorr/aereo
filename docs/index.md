<p align="center">
    <img src="banner.svg" alt="AEREO logo" style="max-width: 300px; width: 100%;">
</p>

---

Satellite data lives in a dozen different catalogs, each with its own API,
authentication, and file format. **AEREO** unifies them into a single pipeline:
**search** across catalogs, **prepare** extraction tasks on a shared grid, and
**execute** them through the backend of your choice — from a local notebook to
AWS Lambda.

<div class="grid cards" markdown>

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

    Use Hydra config packages with `AereoClient` or the `aereo` CLI.

    [:octicons-arrow-right-24: Run Aereo](run/index.md)

-   ## Build a plugin

    ---

    Add a new search provider, reader, or writer. Like PyTorch modules:
    implement `__call__` and register via entry points.

    [:octicons-arrow-right-24: Learn How](plugins/plugin-overview.md)

-   ## API Reference

    ---

    Explore the complete API for power users and plugin developers.

    [:octicons-arrow-right-24: View API](api/client.md)

</div>

---

## 10-line example

```python
from aereo.pipeline import ExtractionJob
from aereo.client import AereoClient
from aereo.backends import LocalProcessBackend

# Load a Hydra config package (search + grid + patch + extract)
job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")
client = AereoClient()

# 1. Search   2. Prepare tasks   3. Execute
results = client.search(job.search)
tasks = client.build_tasks(results, job=job)
artifacts = client.execute_tasks(tasks, backend=LocalProcessBackend(max_workers=2))
```

Open `job.output_uri` — you have GeoTIFFs on the Major TOM grid.

---

## How AEREO works

```text
┌─────────┐     ┌──────────────┐     ┌────────────────────┐     ┌───────────┐
│  Search │ ──▶ │ Prepare tasks│ ──▶ │ Execute on backend │ ──▶ │  EOIDS    │
│ provider│     │ Grid + Patch │     │ Local / Lambda     │     │ GeoTIFFs  │
└─────────┘     └──────────────┘     └────────────────────┘     └───────────┘
```

1. **Search** — a `SearchProvider` queries a catalog and returns a validated
   `GeoDataFrame[AssetSchema]`.
2. **Prepare** — AEREO builds grid cells over your AOI, groups assets by time,
   and chunks them into `ExtractionTask` objects.
3. **Execute** — a backend runs each task through a stage pipeline:
   `Reader → Processor → Reprojector → Processor → Writer`.

All of this is configurable through Hydra YAML files or plain Python objects.

---

Apache License 2.0
