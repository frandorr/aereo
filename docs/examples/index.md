# Examples

AerEO ships with runnable Jupyter notebooks for every supported sensor and
workflow. Each notebook uses the Hydra config package in `examples/config` and
the `ExtractionJob` API: `search`, `build_tasks`, and `execute`.

The thumbnails below are real outputs from the notebooks — grid-aligned patches
on the Major TOM grid, with the target AOI overlaid.

## Before you run

Most examples perform live catalog searches and data downloads. Make sure you
have:

1. The **core package and any sensor-specific plugins** listed below.
2. **Credentials** for the catalog that requires them.
3. A few minutes of runtime for the extraction step.

## Beginner

| Notebook | Sensor | Plugins | Auth | What it teaches | Preview |
|---|---|---|---|---|---|
| [01 — Sentinel-2 (nir, red)](01-sentinel2.ipynb) | Sentinel-2 MSI | `aereo` | None (Earth Search is public) | Load a Hydra job, search STAC, extract a GeoTIFF on the Major TOM grid. | ![Sentinel-2](../assets/images/01-sentinel2-plot-patches.png) |
| [05 — GOES-19 ABI preview](05-goes19.ipynb) | GOES-19 ABI | `aereo` + `aereo-search-aws-goes` + `aereo-read-satpy` | None | Public S3 search and Satpy-based reading/reprojection. | ![GOES-19](../assets/images/05-goes19-bed3cf89.png) |
| [step_by_step_raw](step_by_step_raw.ipynb) | Sentinel-2 MSI | `aereo` | None (Earth Search is public) | Same pipeline built entirely from raw Python — no config files or Hydra. | ![Sentinel-2 raw](../assets/images/step_by_step_raw-visualise.png) |

## Processing

| Notebook | Sensor | Plugins | Auth | What it teaches | Preview |
|---|---|---|---|---|---|
| [01b — Sentinel-2 NDVI](01b-sentinel2-ndvi.ipynb) | Sentinel-2 MSI | `aereo` | None (Earth Search is public) | Add a processor stage (`NDVI`) before reprojection. | ![Sentinel-2 NDVI](../assets/images/01b-sentinel2-ndvi-plot-patches.png) |
| [01c — Sentinel-2 NDWI](01c-sentinel2-ndwi.ipynb) | Sentinel-2 MSI | `aereo` | None (Earth Search is public) | Add a processor stage (`NDWI`) before reprojection. | ![Sentinel-2 NDWI](../assets/images/01c-sentinel2-ndwi-search-sentinel2.png) |
| [03b — Sentinel-3 NDVI](03b-sentinel3-ndvi.ipynb) | Sentinel-3 OLCI | `aereo` + `aereo-read-satpy` | NASA Earthdata | Processor stage with Satpy-based reading. | ![Sentinel-3 NDVI](../assets/images/03b-sentinel3-ndvi-2d4730ca.png) |

## Sensors

| Notebook | Sensor | Plugins | Auth | What it teaches | Preview |
|---|---|---|---|---|---|
| [02 — VIIRS](02-viirs.ipynb) | VIIRS | `aereo` + `aereo-read-satpy` | NASA Earthdata | Search Earthaccess and read with Satpy. | ![VIIRS](../assets/images/02-viirs-plot-patches.png) |
| [03 — Sentinel-3 OLCI](03-sentinel3.ipynb) | Sentinel-3 OLCI | `aereo` + `aereo-read-satpy` | NASA Earthdata | Sentinel-3 extraction workflow. | ![Sentinel-3 OLCI](../assets/images/03-sentinel3-2d4730ca.png) |
| [04 — Tessera](04-tessera.ipynb) | GeoTessera | `aereo` + `aereo-search-tessera` + `aereo-read-tessera` | None | Tessera tile search and extraction. | ![Tessera](../assets/images/04-tessera-2d4730ca.png) |
| [06 — Multiple constellations](06-multiple-constellation.ipynb) | Sentinel-2 + VIIRS | `aereo` + `aereo-read-satpy` | NASA Earthdata | Search and extract multiple sensors with a shared cache. | ![Multi-constellation](../assets/images/06-multiple-constellation-f6d7b8aa.png) |

## Download notebooks

You can also download the raw notebooks directly from GitHub:

- [01-sentinel2.ipynb](https://github.com/frandorr/aereo/blob/main/examples/01-sentinel2.ipynb)
- [01b-sentinel2-ndvi.ipynb](https://github.com/frandorr/aereo/blob/main/examples/01b-sentinel2-ndvi.ipynb)
- [01c-sentinel2-ndwi.ipynb](https://github.com/frandorr/aereo/blob/main/examples/01c-sentinel2-ndwi.ipynb)
- [02-viirs.ipynb](https://github.com/frandorr/aereo/blob/main/examples/02-viirs.ipynb)
- [03-sentinel3.ipynb](https://github.com/frandorr/aereo/blob/main/examples/03-sentinel3.ipynb)
- [03b-sentinel3-ndvi.ipynb](https://github.com/frandorr/aereo/blob/main/examples/03b-sentinel3-ndvi.ipynb)
- [04-tessera.ipynb](https://github.com/frandorr/aereo/blob/main/examples/04-tessera.ipynb)
- [05-goes19.ipynb](https://github.com/frandorr/aereo/blob/main/examples/05-goes19.ipynb)
- [06-multiple-constellation.ipynb](https://github.com/frandorr/aereo/blob/main/examples/06-multiple-constellation.ipynb)
- [step_by_step_raw.ipynb](https://github.com/frandorr/aereo/blob/main/examples/step_by_step_raw.ipynb)
