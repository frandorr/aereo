# AER CLI

AER ships with a command-line interface for users who prefer YAML configuration over Python notebooks. Every CLI command uses `LocalProcessBackend` under the hood.

---

## Installation

The CLI is included with `aereo`:

```bash
pip install aereo aereo-search-aws-goes aereo-extract-satpy
```

---

## Verify plugins

List every search and extract plugin AER can discover:

```bash
aereo plugins
```

If a plugin is missing, install the corresponding pip package and run the command again.

---

## One-shot extraction

`aereo run` performs search → prepare → extract in a single command.

```bash
aereo run \
  --profile goes.yaml \
  --geojson chocon.geojson \
  --start 2026-04-02T14:00 \
  --end 2026-04-02T14:10 \
  --output-dir ./out
```

**Options:**

| Option | Short | Required | Description |
|--------|-------|:--------:|-------------|
| `--profile` | `-p` | ✅ | Path to profile YAML (repeatable) |
| `--config` | `-c` | — | Path to grid config YAML |
| `--geojson` | `-g` | — | Path to AOI GeoJSON file |
| `--start` | `-s` | — | Start datetime (ISO 8601) |
| `--end` | `-e` | — | End datetime (ISO 8601) |
| `--output-dir` | `-d` | — | Output directory (default: `out`) |
| `--workers` | `-w` | — | Max batch workers (default: `1`) |
| `--cells-per-chunk` | — | — | Max grid cells per task (default: `50`) |
| `--verbose` | `-v` | — | Enable verbose logging |

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (invalid config, missing file, extraction failure) |
| `2` | No results found for the given search criteria |

---

## Example YAML files

### Profile (`goes.yaml`)

```yaml
profiles:
  - name: goes_c02
    resolution: 1000
    collections:
      ABI-L1b-RadF: ["C02"]
    extract_params:
      reader: abi_l1b
      calibration: reflectance
    search_params:
      satellite: GOES-19
    plugin_hints:
      search: search_aws_goes
      extract: extract_satpy
```

### Grid config (`grid.yaml`)

```yaml
grid_config:
  target_grid_dist: 50000
  target_grid_overlap: false
  target_grid_margin: 6.8
  grid_filter_mode: intersection
```

These files are also available in `examples/data/` in the repository.

---

## Step-by-step pipeline

For finer control, run each phase separately. This is useful when you want to inspect search results before committing to extraction.

### 1. Search

```bash
aereo search \
  --profile goes.yaml \
  --geojson aoi.geojson \
  --start 2026-04-02T14:00 \
  --end 2026-04-02T14:10 \
  --output results.json
```

`results.json` contains a GeoDataFrame of matching assets. Review it before proceeding.

### 2. Prepare

```bash
aereo prepare \
  --profile goes.yaml \
  --config grid.yaml \
  --output-dir ./out \
  --output tasks.pkl \
  results.json
```

`tasks.pkl` contains the chunked extraction tasks.

### 3. Extract

```bash
aereo extract \
  --output-dir ./out \
  --workers 4 \
  tasks.pkl
```

Extracted GeoTIFFs are written to `--output-dir` in [EOIDS](eoids.md) format.

---

## Validate configs before running

Catch schema errors before starting a long extraction:

```bash
# Validate a profile
aereo validate --profile goes.yaml

# Validate a grid config
aereo validate --config grid.yaml
```

Validation exits with code `0` on success and code `1` on failure, printing the specific validation error.

---

## Tips

- **Multiple profiles** — pass `--profile` more than once to extract several sensors in one run:
  ```bash
  aereo run -p goes.yaml -p s2.yaml -g aoi.geojson --start 2026-04-02T14:00 --end 2026-04-02T14:10
  ```
- **Date formats** — any ISO 8601 string works (`2026-04-02`, `2026-04-02T14:00`, `2026-04-02T14:00:00Z`).
- **AOI from GeoJSON** — the file can be a `Feature`, `FeatureCollection`, or raw `Geometry`. AER uses the first feature found.
- **No results?** — narrow your date range, check your `search_params` (e.g., `satellite: GOES-19`), or verify the collection name exists for that sensor.
