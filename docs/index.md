# aer 🪐

> **One pip install. One code block. One PNG.**
> Plugin-based satellite data extraction — from search to analysis-ready GeoTIFF in minutes.

![Same grid cell (loc-16D20L) viewed by four different sensors: GOES-19 ABI, MODIS Terra, VIIRS NOAA-21, and Sentinel-3 OLCI](examples/visualization/single_cell_comparison.png)

---

## Copy-Paste → PNG

```bash
pip install aer-eo aer-search-aws-goes aer-extract-satpy
```

```python
from datetime import datetime, timezone
from aer.client import AerClient
from aer.interfaces import ExtractionProfile
import rasterio, matplotlib.pyplot as plt

client = AerClient()
results = client.search(
    collections=["ABI-L1b-RadF"],
    start_datetime=datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 1, 15, 10, tzinfo=timezone.utc),
    search_params={"ABI-L1b-RadF": {"satellite": "GOES-19"}},
)
profiles = [ExtractionProfile(
    name="c07", resolution=2000,
    collection_variables_map={"ABI-L1b-RadF": ["C07"]},
    extract_params={"reader": "abi_l1b"},
)]
tasks = client.prepare_for_extraction(results, profiles=profiles, uri="out")
artifacts = client.extract_batches(tasks)

# Render first GeoTIFF to PNG
with rasterio.open(artifacts[0].path) as src:
    plt.imsave("my_first_cell.png", src.read(1), cmap="viridis")
print(f"PNG saved: my_first_cell.png")
```

---

## 🌐 Built on Major TOM

`aer` is one of the first frameworks to standardize on the [**Major TOM**](https://github.com/ESA-PhiLab/Major-TOM) grid — a globally uniform spatial index that makes pixels align across any sensor. Data extracted by `aer` is interoperable with the [Major TOM ecosystem](https://huggingface.co/Major-TOM).

---

## Documentation

| Document | Description |
|----------|-------------|
| [Installation](installation.md) | Setup for users and developers |
| [Pipeline Architecture](pipeline-architecture.md) | Three-phase pipeline with UML diagrams and data flow |
| [Plugin System](plugins.md) | How plugins are discovered and routed |
| [Build Your Own Plugin](build-your-own-plugin.md) | Developer guide for creating new plugins |
| [EOIDS](eoids.md) | Output file structure convention (BIDS-inspired) |
| [API Reference](api/client.md) | Python API documentation |

---

## Quick Links

- **Repository**: [github.com/frandorr/aer](https://github.com/frandorr/aer)
- **Issues**: [github.com/frandorr/aer/issues](https://github.com/frandorr/aer/issues)
- **License**: Apache License 2.0
