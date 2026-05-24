# aer 🪐

> Plugin-based satellite data extraction — from search to analysis-ready Major TOM grid in minutes.

---

## Install

Pick your sensor and copy-paste:

```bash
# GOES ABI (public S3, no auth)
pip install aer-eo aer-search-aws-goes aer-extract-satpy

# Sentinel-2 (Planetary Computer)
pip install aer-eo aer-search-planetary-computer aer-extract-odc-stac

# MODIS / VIIRS / Sentinel-3 (NASA Earthdata)
pip install aer-eo aer-search-earthaccess aer-extract-satpy
```

> **Note:** The PyPI package is `aer-eo` because `aer` is already taken.

---

## 10-line example

```python
from datetime import datetime, timezone
from aer.client import AerClient
from aer.interfaces import AerProfile, GridConfig
from shapely.geometry import box

client = AerClient()
aoi = box(-70, -40, -68, -39)
profile = AerProfile(name="goes", resolution=1000, collections={"ABI-L1b-RadF": ["C01"]}, plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"}, search_params={"satellite": "GOES-19"}, extract_params={"reader": "abi_l1b"})
results = client.search(profiles=[profile], start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc), end_datetime=datetime(2026, 4, 2, 14, 10, tzinfo=timezone.utc), intersects=aoi)
tasks = client.prepare_for_extraction(results, profiles=[profile], uri="./out", grid_config=GridConfig(target_grid_dist=256000), target_aoi=aoi)
client.execute_tasks(tasks)
```

Open `./out/` — you have GeoTIFFs.

---

## Docs & Examples

- [Quick Start](https://frandorr.github.io/aer/quickstart/) — first extraction in 3 minutes
- [Examples](https://frandorr.github.io/aer/examples/) — GOES, Sentinel-2, multi-sensor, ML-ready
- [CLI](https://frandorr.github.io/aer/cli/) — zero-code `aer run`
- [Build a Plugin](https://frandorr.github.io/aer/build-your-own-plugin/) — extend AER

---

Apache License 2.0
