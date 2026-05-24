<p align="center">
    <img src="aer.png" alt="AER logo" style="max-width: 500px; width: 100%;">
</p>

<h1 align="center">
  Plugin-based satellite data extraction — from search to analysis-ready Major TOM grid in minutes.
</h1>

---

## Install

Pick your sensor and copy-paste:

=== "GOES ABI (public S3, no auth)"

    ```bash
    pip install aer-eo aer-search-aws-goes aer-extract-satpy
    ```

=== "Sentinel-2 (Planetary Computer)"

    ```bash
    pip install aer-eo aer-search-planetary-computer aer-extract-odc-stac
    ```

=== "MODIS / VIIRS / Sentinel-3 (NASA Earthdata)"

    ```bash
    pip install aer-eo aer-search-earthaccess aer-extract-satpy
    ```

> **Note:** The PyPI package is `aer-eo` because `aer` is already taken.

---

## 10-line example

```python
from aer.client import AerClient
from aer.interfaces import AerProfile, GridConfig
from shapely.geometry import box

client = AerClient()
profile = AerProfile(
    name="goes",
    resolution=1000,
    collections={"ABI-L1b-RadF": ["C01"]},
    plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
    search_params={"satellite": "GOES-19"},
    extract_params={"reader": "abi_l1b"},
)
results = client.search(profiles=[profile], start_datetime=..., end_datetime=..., intersects=box(-70, -40, -68, -39))
tasks = client.prepare_for_extraction(results, profiles=[profile], uri="./out", grid_config=GridConfig(target_grid_dist=256000))
client.execute_tasks(tasks)
```

Open `./out/` — you have GeoTIFFs.

---

## New to AER?

- [Quick Start](quickstart.md) — first extraction in 3 minutes
- [CLI](cli.md) — zero-code `aer run`

## Going deeper

- [Examples](examples.md) — GOES, Sentinel-2, multi-sensor, ML-ready
- [Grid System](grid.md) — how the Major TOM grid works

---

Apache License 2.0
