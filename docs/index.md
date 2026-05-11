<p align="center">
  <!-- BANNER IMAGE PLACEHOLDER -->
  <!-- Replace the line below with your banner image -->
  <!-- <img src="..." alt="AER banner"> -->
</p>

<h1 align="center">aer 🪐</h1>

<p align="center">
  <strong>One pip install. One code block. One PNG.</strong>
</p>

<p align="center">
  Plugin-based satellite data extraction — from search to analysis-ready GeoTIFF in minutes.
</p>

<p align="center">
  <!-- HERO IMAGE PLACEHOLDER -->
  <!-- Replace the line below with a hero/demo image -->
  <!-- <img src="..." alt="AER demo"> -->
</p>

---

## What is AER?

**AER** is a Python framework that makes extracting satellite imagery as easy as running a few lines of code. It handles the entire pipeline — **search**, **prepare**, and **extract** — so you can go from raw sensor archives to a grid-aligned GeoTIFF (or PNG) in minutes, not hours.

Whether you are working with **GOES**, **MODIS**, **VIIRS**, **Sentinel-2**, or **Sentinel-3**, AER lets you mix and match sensors through a unified interface. No need to learn a different API for every data provider.

<p align="center">
  <!-- ARCHITECTURE DIAGRAM PLACEHOLDER -->
  <!-- Replace the line below with an architecture/overview image -->
  <!-- <img src="..." alt="AER pipeline overview"> -->
</p>

---

## The key benefits

### 🚀 **AER is fast to learn and fast to run**

- **One code block** gets you from install to a rendered PNG.
- **Declarative profiles** define what you want to extract — resolution, variables, and sensor settings in a single object.
- **Batch extraction** handles multiple granules and grid cells in one call.
- **Configuration-driven** — load extraction profiles from YAML or JSON and keep your experiments reproducible.

### 🔌 **Plugins unlock any sensor**

- **Swap sensors without rewriting code** — the same `AerClient` API works for GOES, MODIS, VIIRS, Sentinel-2, Sentinel-3, and more.
- **Plugin ecosystem** — install only what you need: search plugins find the data, extract plugins process it.
- **Build your own** — implementing a new `SearchProvider` or `Extractor` is standard Python packaging with entry points. AER discovers them automatically.

### 🌐 **Major TOM grid = interoperable pixels**

- **Globally uniform spatial index** — every cell shares the same UTM-aligned footprint regardless of sensor.
- **Pixels align across sensors** — compare GOES, MODIS, and Sentinel data in the same grid cell without manual reprojection.
- **Interoperable with the Major TOM ecosystem** — extracted data drops straight into the [Major TOM](https://huggingface.co/Major-TOM) tooling and models.

---

## Copy-Paste → PNG

```bash
pip install aer-eo aer-search-aws-goes aer-extract-satpy
```

```python
from datetime import datetime, timezone
from aer.client import AerClient
from aer.interfaces import AerProfile
import rasterio, matplotlib.pyplot as plt

client = AerClient()
profiles = [
    AerProfile(
        name="c07",
        resolution=2000,
        collections={"ABI-L1b-RadF": ["C07"]},
        search_params={"satellite": "GOES-19"},
        extract_params={"reader": "abi_l1b"},
    )
]
results = client.search(
    profiles=profiles,
    start_datetime=datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 1, 15, 10, tzinfo=timezone.utc),
)
tasks = client.prepare_for_extraction(results, profiles=profiles, uri="out")
artifacts = client.extract_batches(tasks)

# Render first GeoTIFF to PNG
with rasterio.open(artifacts[0].path) as src:
    plt.imsave("my_first_cell.png", src.read(1), cmap="viridis")
print(f"PNG saved: my_first_cell.png")
```

<p align="center">
  <!-- EXAMPLE OUTPUT IMAGE PLACEHOLDER -->
  <!-- Replace the line below with a sample output image -->
  <!-- <img src="..." alt="Sample AER output"> -->
</p>

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
