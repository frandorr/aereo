# aer 🪐

**aer** (from the Greek word for *air*) is a plugin-based Python framework for satellite data discovery, extraction, and processing. Install only the sensor plugins you need — `aer` handles search, spatial gridding, and extraction into analysis-ready GeoTIFFs.

> From zero to analysis-ready satellite GeoTIFFs in minutes.

![Same grid cell (loc-16D20L) viewed by four different sensors: GOES-19 ABI, MODIS Terra, VIIRS NOAA-21, and Sentinel-3 OLCI](examples/visualization/single_cell_comparison.png)

---

## 🌐 Built on Major TOM

`aer`'s spatial grid engine is built on [**Major TOM**](https://github.com/ESA-PhiLab/Major-TOM) (Terrestrial Observation Metaset), an open framework by [ESA Φ-lab](https://huggingface.co/ESA-philab) for curating large-scale Earth Observation datasets.

Major TOM provides a **globally uniform grid** that partitions Earth's surface into consistent cells with standard UTM projections — ensuring pixel-perfect alignment across different sensors and resolutions.

`aer` extends this with `GridDefinition` (generates cells over any polygon), `GridCell` (carries unique ID, CRS, and resampling footprint), and `area_def()` (builds [pyresample](https://pyresample.readthedocs.io/)-compatible area definitions). Data extracted by `aer` is spatially indexed and interoperable with the [Major TOM ecosystem](https://huggingface.co/Major-TOM).

> 📄 *Major TOM: Expandable Datasets for Earth Observation* — [arxiv.org/abs/2402.12095](https://arxiv.org/abs/2402.12095)

---

## 📡 Extensible by Design

`aer` is **not limited to a fixed set of sensors**. It is a plugin-based framework — any satellite mission can be supported by installing or writing a plugin. The `aer-search-earthaccess` plugin alone can search [any collection available in NASA's CMR catalog](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html), and `aer-extract-satpy` can extract data for [any reader supported by Satpy](https://satpy.readthedocs.io/en/stable/). The combination covers **hundreds of missions and products** out of the box.

Here are some examples of sensor configurations that have been tested end-to-end:

| Sensor | Example Collection(s) | Search Plugin | Extract Plugin | Auth |
|--------|----------------------|---------------|----------------|:----:|
| GOES ABI | `ABI-L1b-RadF`, `ABI-L2-AODF` | `aer-search-aws-goes` | `aer-extract-satpy` | None ✅ |
| MODIS Terra | `MOD021KM` | `aer-search-earthaccess` | `aer-extract-satpy` | Earthdata 🔐 |
| Sentinel-2 MSI | *(via STAC)* | `aer-search-pc-sentinel2` | `aer-extract-pc-sentinel2` | None ✅ |
| Sentinel-3 OLCI | `S3A_OL_1_EFR` | `aer-search-earthaccess` | `aer-extract-satpy` | None ✅ |
| VIIRS (NOAA-21) | `VJ202IMG`, `VJ203IMG` | `aer-search-earthaccess` | `aer-extract-satpy` | Earthdata 🔐 |

> Collection names are **case-insensitive** — `abi-l1b-radf` and `ABI-L1b-RadF` both work.
>
> Want to add a new sensor or data source? Write a plugin in ~50 lines — see the [Plugin Developer Guide](./docs/build-your-own-plugin.md).

---

## ⚡️ Quickstart

### 1. Install

```bash
# Core + GOES plugins (public S3, no auth needed)
pip install aer-eo aer-search-aws-goes aer-extract-satpy
```

### 2. Search → Prepare → Extract

`aer` follows a three-step pipeline: **Search** (discover granules), **Prepare** (generate grid-aligned tasks), and **Extract** (download and process into GeoTIFFs).

```python
from datetime import datetime, timezone
from aer.client import AerClient
from aer.interfaces import ExtractionProfile

# Initialize — auto-discovers installed plugins
client = AerClient()

# 1. Search: find granules intersecting your AOI
search_results = client.search(
    collections=["ABI-L1b-RadF"],
    start_datetime=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
    search_params={"ABI-L1b-RadF": {"satellite": "GOES-19"}},
)

# 2. Prepare: define what to extract and generate grid-aligned tasks
profiles = [
    ExtractionProfile(
        name="goes_c07",
        resolution=2000,
        collection_variables_map={"ABI-L1b-RadF": ["C07"]},
        extra_params={"reader": "abi_l1b"},
    )
]
tasks = client.prepare_for_extraction(
    search_results,
    profiles=profiles,
    uri="output/goes_extraction",
)

# 3. Extract: download, resample, and write GeoTIFFs
artifacts = client.extract_batches(
    tasks,
    extract_params={"padding": 2, "resampling": "nearest", "calibration": "radiance"},
    max_batch_workers=4,
)
print(f"Done! {len(artifacts)} GeoTIFFs written.")
```

> [!TIP]
> Use `max_batch_workers` to parallelize extraction across CPU cores.

---

## 🔌 Plugin System

Plugins are standard Python packages that declare `SearchProvider` or `Extractor` interfaces and register via `entry_points`. The `AerRegistry` discovers them at runtime — no manual wiring needed.

```python
from aer.registry import AerRegistry
registry = AerRegistry()
print(registry.list_supported_collections())
```

To create a plugin, subclass the interface and register it in your `pyproject.toml`:

```python
from aer.interfaces import SearchProvider

class MySearch(SearchProvider):
    supported_collections = ["my-sensor-l1"]
    def search(self, collections, **kwargs):
        ...
```

```toml
[project.entry-points."aer.plugins"]
my_search = "my_package:MySearch"
```

Full tutorial → [Plugin Developer Guide](./docs/build-your-own-plugin.md)

---

## 🤝 Development

```bash
git clone https://github.com/frandorr/aer.git && cd aer && uv sync
uv run pytest test/components/aer/spatial/   # test one component
uv run pytest                                 # full suite
uv run poly create component --name my_feat   # add a new component
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Pipeline Architecture](docs/pipeline-architecture.md) | Three-phase pipeline with UML diagrams and data flow |
| [EOIDS Format](docs/eoids.md) | Output file structure convention (BIDS-inspired) |
| [Plugin System](docs/plugins.md) | How plugins are discovered and routed |
| [Build Your Own Plugin](docs/build-your-own-plugin.md) | Step-by-step guide for custom search/extract plugins |
| [Installation Guide](docs/installation.md) | Core + plugin installation for users and developers |
| [Examples](examples/README.md) | Jupyter notebooks for every supported sensor |

---

## 📄 License

MIT License
