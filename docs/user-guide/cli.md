# CLI

AerEO ships with a Hydra-driven CLI. If you have already built a config
package, you can run the same pipeline from the terminal without writing extra
Python. See the [Configuration](../configuration/config-package.md) section for
how the config package is laid out.

## Run the full pipeline

```bash
cd examples/config

aereo action=run \
  search=sentinel2_pc \
  grid_dist=grid_10km \
  read=sentinel2 \
  write=sentinel2
```

`action=run` performs search, build-tasks, and execute in one command.

## Individual stages

```bash
# Search only
aereo action=search search=sentinel2_pc

# Build tasks from saved assets
aereo action=build-tasks search=sentinel2_pc

# Extract from saved tasks
aereo action=extract search=sentinel2_pc

# Validate a config package without network calls
aereo action=validate search=sentinel2_pc
```

## Discover plugins

```bash
# List installed plugins
aereo action=plugins

# Show parameters for a plugin
aereo action=plugin_params plugin=search_stac
```

## Override config values

Hydra-style overrides work on the command line:

```bash
aereo action=run \
  search=sentinel2_pc \
  grid_dist=grid_50km \
  read=sentinel2 \
  write=sentinel2 \
  target_aoi=aoi/cordoba.geojson
```

## Dry run

Set `DRY_RUN=true` to validate the configuration and task graph without making
network calls or writing files:

```bash
DRY_RUN=true aereo action=run search=sentinel2_pc read=sentinel2 write=sentinel2
```
