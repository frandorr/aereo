# Hydra Overrides

Because AerEO jobs are Hydra configs, you can override any value without
creating a new YAML file. Overrides work the same way in Python, in the CLI, and
in Lambda launchers.

## Overrides from Python

Pass a list of `key=value` strings to `ExtractionJob.load_from_config`:

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
    overrides=[
        "grid_dist=grid_50km",
        "target_aoi=aoi/cordoba.geojson",
        "output_uri=/tmp/aereo_cordoba",
    ],
)

print(job.grid_dist)  # 50000
print(job.output_uri)  # /tmp/aereo_cordoba
```

The right-hand side can be:

- A literal value (`grid_dist=50000`).
- A config-group selection (`grid_dist=grid_10km`), which Hydra resolves from the
  `grid_dist/` directory.
- A path to a GeoJSON file (`target_aoi=aoi/cordoba.geojson`).

## Overrides from the CLI

The `aereo` CLI is a Hydra application, so all overrides use the same syntax:

```bash
cd examples/config

aereo action=run \
  search=sentinel2_pc \
  grid_dist=grid_10km \
  read=sentinel2 \
  write=sentinel2
```

You can also override `target_aoi`, `output_uri`, `resolution`, `workers`, and
any other field exposed by the CLI default config:

```bash
aereo action=run \
  search=sentinel2_pc \
  grid_dist=grid_50km \
  read=sentinel2 \
  write=sentinel2 \
  target_aoi=aoi/cordoba.geojson
```

## Running individual stages

Hydra overrides apply to every CLI action:

```bash
# Search only
aereo action=search search=sentinel2_pc

# Build tasks from saved search results
aereo action=build-tasks search=sentinel2_pc

# Extract from saved tasks
aereo action=extract search=sentinel2_pc

# Validate the config without network calls
aereo action=validate search=sentinel2_pc
```

## Dry run

Set `DRY_RUN=true` to validate the configuration, plugin instantiation, and task
graph without making network calls or writing files:

```bash
DRY_RUN=true aereo action=run search=sentinel2_pc read=sentinel2 write=sentinel2
```

The same flag works for Python scripts:

```bash
DRY_RUN=true uv run python examples/config/run_job.py
```

## Composition order

Hydra applies overrides **after** `defaults:` composition. This means a root job
file can set a value, a config group can set a value, and your override wins
last. For example:

1. `job_sentinel2.yaml` sets `grid_dist: 10_000`.
2. `defaults: [job_sentinel2, _self_]` keeps that value unless overridden.
3. `overrides=["grid_dist=grid_50km"]` changes it to 50 km.

## Next steps

- [Config Package](config-package.md) — understand the directory layout.
- [YAML Schema](yaml-schema.md) — every job field explained.
- [CLI](../user-guide/cli.md) — full command reference.
