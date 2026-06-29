# Examples Gallery

AEREO ships with runnable Jupyter notebooks for every supported sensor and
workflow. Each notebook uses a Hydra config package from `examples/config` and
the `ExtractionJob` orchestration API: `search`, `build_tasks`, and `execute`.

The notebooks are executed during the docs build, so the rendered pages show
real outputs. You can also run them locally from the repo.

---

## Before you run

Most examples perform live catalog searches and data downloads. Make sure you
have:

1. **The core package and any sensor-specific plugins** listed in the table
   below.
2. **Credentials** for the catalog that requires them (Earthdata,
   Planetary Computer subscription key).
3. **A few minutes of runtime** for the extraction step.

---

## Beginner

| Notebook | Sensor | Plugins | Auth | What it teaches |
|----------|--------|---------|------|-----------------|
| [01 — Sentinel-2 true-color](01-sentinel2.ipynb) | Sentinel-2 MSI | `aereo` built-ins + `aereo-search-planetary-computer` | Planetary Computer key (recommended) | Load a Hydra job, search STAC, extract a GeoTIFF on the Major TOM grid. |
| [05 — GOES-19 ABI preview](05-goes19.ipynb) | GOES-19 ABI | `aereo-search-aws-goes` + `aereo-read-satpy` + `aereo-reproject-satpy` | None | Public S3 search and Satpy-based reading/reprojection. |

## Processing

| Notebook | Sensor | Plugins | Auth | What it teaches |
|----------|--------|---------|------|-----------------|
| [01b — Sentinel-2 NDVI](01b-sentinel2-ndvi.ipynb) | Sentinel-2 MSI | `aereo` built-ins + `aereo-search-planetary-computer` | Planetary Computer key (recommended) | Add a processor stage (`NDVI`) before reprojection. |
| [03b — Sentinel-3 NDVI](03b-sentinel3-ndvi.ipynb) | Sentinel-3 OLCI | `aereo-search-earthaccess` + `aereo-read-satpy` | NASA Earthdata | Processor stage with Satpy-based reading. |

## Sensors

| Notebook | Sensor | Plugins | Auth | What it teaches |
|----------|--------|---------|------|-----------------|
| [02 — VIIRS](02-viirs.ipynb) | VIIRS | `aereo-search-earthaccess` + `aereo-read-satpy` + `aereo-reproject-satpy` | NASA Earthdata | Search Earthaccess and read with Satpy. |
| [03 — Sentinel-3 OLCI](03-sentinel3.ipynb) | Sentinel-3 OLCI | `aereo-search-earthaccess` + `aereo-read-satpy` + `aereo-reproject-satpy` | NASA Earthdata | Sentinel-3 extraction workflow. |
| [04 — Tessera](04-tessera.ipynb) | GeoTessera | `aereo-search-tessera` + `aereo-read-tessera` | Depends on catalog | Tessera tile search and extraction. |

---

## Run a notebook

```bash
cd examples
jupyter lab 01-sentinel2.ipynb
```

Or convert it to a script:

```bash
jupyter nbconvert --to script 01-sentinel2.ipynb
python 01-sentinel2.py
```

---

## Run the same config from a script

Every notebook config can also be run from the example script that loads the
job, search provider, and task builder from the config package:

```bash
cd examples
uv run python config/run_job.py
```

Override the job, search provider, or task builder by passing flags:

```bash
cd examples
uv run python config/run_job.py --config-name job_goes19 --search goes19 --task-builder grouped
```

Set ``DRY_RUN=true`` to validate the configuration without performing network
calls:

```bash
cd examples
DRY_RUN=true uv run python config/run_job.py
```

See [Run with CLI](../run/run-with-cli.md) for the full CLI reference.
