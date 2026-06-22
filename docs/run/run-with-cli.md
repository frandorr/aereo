# Run with CLI

AEREO ships with a Hydra-native command-line interface. Every command uses the
same config packages as the Python API, so a notebook pipeline and a CLI
pipeline can share the exact same YAML files.

---

## Installation

The CLI is included with the `aereo` package:

```bash
pip install aereo aereo-search-planetary-computer
```

---

## Verify plugins

List every installed plugin:

```bash
aereo action=plugins
```

Inspect a plugin's parameters:

```bash
aereo action=plugin_params plugin_name=SearchSTAC
```

---

## One-shot extraction: `action=run`

`aereo action=run` performs search → prepare → extract in a single command. It
expects the same Hydra config groups used by `ExtractionJob.load_from_config()`:

```bash
cd examples/config
aereo action=run \
  search=sentinel2_pc \
  grid_config=grid_10km \
  patch_config=patch_10m \
  extract=sentinel2 \
  output_uri=/tmp/aereo_cli
```

Because the config directory is the current working directory, Hydra finds the
`search/`, `grid_config/`, `patch_config/`, and `extract/` subdirectories
automatically.

---

## CLI actions

| Action | Purpose |
|--------|---------|
| `run` | Search → prepare → extract in one command. |
| `search` | Run only the search step and print or save results. |
| `prepare` | Build `ExtractionTask` objects from saved search results. |
| `extract` | Run extraction from saved tasks. |
| `validate` | Validate a config package without running network calls. |
| `plugins` | List installed plugins. |
| `plugin_params` | Show parameters for one plugin. |

---

## Step-by-step pipeline

For finer control, run each phase separately. This is useful when you want to
inspect search results before committing to extraction.

### 1. Search

```bash
aereo action=search \
  search=sentinel2_pc \
  output=results.json
```

`results.json` contains a GeoDataFrame of matching assets. Review it before
proceeding.

### 2. Prepare

```bash
aereo action=prepare \
  search_results=results.json \
  grid_config=grid_10km \
  patch_config=patch_10m \
  extract=sentinel2 \
  output_uri=/tmp/aereo_cli \
  output=tasks.pkl
```

`tasks.pkl` contains the chunked extraction tasks.

### 3. Extract

```bash
aereo action=extract \
  tasks=tasks.pkl \
  output_dir=/tmp/aereo_cli \
  workers=2
```

Extracted GeoTIFFs are written to `output_dir` in [EOIDS](../concepts/output-formats.md)
format. A `artifacts.parquet` file is also written with the full artifact catalog.

---

## Validate before running

Catch schema errors before starting a long extraction:

```bash
aereo action=validate \
  search=sentinel2_pc \
  grid_config=grid_10km \
  patch_config=patch_10m \
  extract=sentinel2
```

Validation exits with code `0` on success and code `1` on failure, printing the
specific validation error.

---

## Common options

All actions support these Hydra-style overrides:

| Override | Example | Description |
|----------|---------|-------------|
| `search=` | `search=sentinel2_pc` | Select a search provider config. |
| `grid_config=` | `grid_config=grid_50km` | Select a grid config. |
| `patch_config=` | `patch_config=high_res` | Select a patch config. |
| `extract=` | `extract=sentinel2_ndvi` | Select an extract stage config. |
| `output_uri=` | `output_uri=/tmp/out` | Base output path. |
| `output_dir=` | `output_dir=/tmp/out` | Used by `extract` action. |
| `workers=` | `workers=4` | Max workers for `LocalProcessBackend`. |
| `cells_per_task=` | `cells_per_task=10` | Grid cells per prepared task. |
| `overwrite=` | `overwrite=true` | Bypass per-task artifact cache. |
| `verbose=` | `verbose=true` | Enable debug logging. |
| `geojson=` | `geojson=aoi/chocon.geojson` | Path to AOI GeoJSON. |
| `start=` / `end=` | `start=2024-01-01T00:00:00Z` | Temporal filter. |

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success. |
| `1` | Error (invalid config, missing file, extraction failure). |
| `2` | No results found for the given search criteria. |

---

## Tips

- **Date formats** — any ISO 8601 string works (`2024-01-01`,
  `2024-01-01T14:00`, `2024-01-01T14:00:00Z`).
- **AOI from GeoJSON** — the file can be a `Feature`, `FeatureCollection`, or
  raw `Geometry`. AEREO uses the first feature found.
- **No results?** — widen your date range, check your collection name, or verify
  the AOI intersects the sensor footprint.
