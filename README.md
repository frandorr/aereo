# aereo 🪐

> Plugin-based satellite data extraction — from search to analysis-ready Major TOM grid in minutes.

---

Satellite data lives in a dozen different catalogs, each with its own API, authentication, and file format. **AER** unifies them into a single pipeline: **search** across catalogs, **extract** assets, and receive everything reprojected to the same **Major TOM grid** — ready for multi-sensor model training.

## Install

Pick your sensor and copy-paste:

```bash
# GOES ABI (public S3, no auth)
pip install aereo aereo-search-aws-goes aereo-extract-satpy

# Sentinel-2 (Planetary Computer)
pip install aereo aereo-search-planetary-computer aereo-extract-odc-stac

# MODIS / VIIRS / Sentinel-3 (NASA Earthdata)
pip install aereo aereo-search-earthaccess aereo-extract-satpy
```

> **Note:** Install the core framework with `pip install aereo`. Plugins are separate packages (e.g. `aereo-search-aws-goes`).

> These plugins ship ready to use. AER's architecture makes adding new sensors trivial — a **search plugin** connects the catalog, an **extract plugin** handles the assets, and reprojection to the **Major TOM grid** happens automatically.

---

## 10-line example

```python
from datetime import datetime, timezone
from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig
from shapely.geometry import box

client = AereoClient()
aoi = box(-70, -40, -68, -39)
profile = AereoProfile(name="goes", resolution=1000, collections={"ABI-L1b-RadF": ["C01"]}, plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"}, search_params={"satellite": "GOES-19"}, extract_params={"reader": "abi_l1b"})
results = client.search(profiles=[profile], start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc), end_datetime=datetime(2026, 4, 2, 14, 10, tzinfo=timezone.utc), intersects=aoi)
tasks = client.prepare_for_extraction(results, profiles=[profile], uri="./out", grid_config=GridConfig(target_grid_dist=256000), target_aoi=aoi)
client.execute_tasks(tasks)
```

Open `./out/` — you have GeoTIFFs.

---

## Docs & Examples

- [Quick Start](https://frandorr.github.io/aereo/quickstart/) — first extraction in 3 minutes
- [Examples](https://frandorr.github.io/aereo/examples/) — GOES, Sentinel-2, multi-sensor, ML-ready
- [CLI](https://frandorr.github.io/aereo/cli/) — zero-code `aereo run`
- [Build a Plugin](https://frandorr.github.io/aereo/build-your-own-plugin/) — extend AER

---

Apache License 2.0
