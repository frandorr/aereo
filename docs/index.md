<p align="center">
    <img src="aer.png" alt="AER logo" style="max-width: 500px; width: 100%;">
</p>

<h1 align="center">
  Plugin-based satellite data extraction — from search to analysis-ready Major TOM grid in minutes.
</h1>

---

Satellite data lives in a dozen different catalogs, each with its own API, authentication, and file format. **AER** unifies them into a single pipeline: **search** across catalogs, **extract** assets, and receive everything reprojected to the same **Major TOM grid** — ready for multi-sensor model training.

## Install

Pick your sensor and copy-paste:

=== "GOES ABI (public S3, no auth)"

    ```bash
    pip install aereo aereo-search-aws-goes aereo-extract-satpy
    ```

=== "Sentinel-2 (Planetary Computer)"

    ```bash
    pip install aereo aereo-search-planetary-computer aereo-extract-odc-stac
    ```

=== "MODIS / VIIRS / Sentinel-3 (NASA Earthdata)"

    ```bash
    pip install aereo aereo-search-earthaccess aereo-extract-satpy
    ```

> **Note:** The PyPI package is `aereo` because `aereo` is already taken.

> These plugins ship ready to use. AER's architecture makes adding new sensors trivial — a **search plugin** connects the catalog, an **extract plugin** handles the assets, and reprojection to the **Major TOM grid** happens automatically.

---

## 10-line example

```python
from datetime import datetime, timezone
from aereo.client import AereoClient
from aereo.interfaces import AereoProfile, GridConfig
from shapely.geometry import box

client = AereoClient()
profile = AereoProfile(
    name="goes",
    resolution=1000,
    collections={"ABI-L1b-RadF": ["C01"]},
    plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
    search_params={"satellite": "GOES-19"},
    extract_params={"reader": "abi_l1b"},
)
results = client.search(
    profiles=[profile],
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 10, tzinfo=timezone.utc),
    intersects=box(-70, -40, -68, -39),
)
tasks = client.prepare_for_extraction(
    results,
    profiles=[profile],
    uri="./out",
    grid_config=GridConfig(target_grid_dist=256000),
)
client.execute_tasks(tasks)
```

Open `./out/` — you have GeoTIFFs.

---

## New to AER?

- [Quick Start](quickstart.md) — first extraction in 3 minutes
- [CLI](cli.md) — zero-code `aereo run`

## Going deeper

- [Examples](examples.md) — GOES, Sentinel-2, multi-sensor, ML-ready
- [Grid System](grid.md) — how the Major TOM grid works

---

Apache License 2.0
