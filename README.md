# aer 🪐

> Plugin-based satellite data extraction — from search to analysis-ready Major TOM grid in minutes.

---

## TL;DR

```python
from aer.client import AerClient
from aer.interfaces import AerProfile

client = AerClient()
results = client.search(profiles=[...], start_datetime=..., end_datetime=...)
tasks = client.prepare_for_extraction(results, profiles=[...], uri="out")
from aer.execution import LocalProcessBackend
backend = LocalProcessBackend()
artifacts = client.execute_tasks(tasks, backend=backend)
```

---

## Why AER?

- **Declarative and reproducible** — Define extraction profiles once (resolution, bands, sensor settings) and run them the same way every time. Load profiles from YAML or JSON to keep experiments reproducible.
- **Plugins unlock any sensor** — The same `AerClient` API works for GOES, MODIS, VIIRS, Sentinel-2, Sentinel-3, and more. Install only the search and extract plugins you need.
- **Major TOM grid = interoperable pixels** — Every cell shares the same UTM-aligned footprint regardless of sensor. Compare data across sensors without manual reprojection, and drop straight into the [Major TOM ecosystem](https://huggingface.co/Major-TOM).

---

## Documentation

| Document | Description |
|----------|-------------|
| [Quick Start](https://frandorr.github.io/aer/quickstart/) | Step-by-step Search → Prepare → Extract walkthrough |
| [Running the Pipeline](https://frandorr.github.io/aer/pipeline/) | Practical guide for `search()`, `prepare_for_extraction()`, and `execute_tasks()` |
| [Using Plugins](https://frandorr.github.io/aer/using-plugins/) | Install core, plugins, and Earthdata auth |
| [Grid System](https://frandorr.github.io/aer/grid/) | Grid definitions, filtering modes, and overlap options |
| [Build Your Own Plugin](https://frandorr.github.io/aer/build-your-own-plugin/) | Developer guide for creating new plugins |
| [API Reference](https://frandorr.github.io/aer/api/client/) | Python API documentation |

Full docs → [frandorr.github.io/aer](https://frandorr.github.io/aer)

---

Apache License 2.0
