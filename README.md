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
**execute** them through the backend of your choice.

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
from aereo.pipeline import ExtractionJob
from aereo.client import AereoClient
from aereo.backends import LocalProcessBackend

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")
client = AereoClient()

results = client.search(job.search)
tasks = client.build_tasks(results, job=job)
artifacts = client.execute_tasks(tasks, backend=LocalProcessBackend(max_workers=2))
```

Open `job.output_uri` — you have GeoTIFFs on the Major TOM grid.

---

## Docs & Examples

- [Your First Pipeline](https://frandorr.github.io/aereo/first-pipeline/) — first extraction in 5 minutes
- [Examples](https://frandorr.github.io/aereo/examples/) — Sentinel-2, VIIRS, Sentinel-3, Tessera, GOES-19
- [Run with CLI](https://frandorr.github.io/aereo/run/run-with-cli/) — zero-code `aereo action=run`
- [Build a Plugin](https://frandorr.github.io/aereo/plugins/build-first-plugin/) — extend AEREO

---

Apache License 2.0
