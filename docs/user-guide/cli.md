# CLI

AerEO ships with a Hydra-driven CLI. If you have already built a config
package, you can run the same pipeline from the terminal without writing extra
Python. See the [Configuration](../configuration/config-package.md) section for
how the config package is laid out.

The CLI config has `search`, `read`, and `write` defaulting to `null`, so you
must use `+` to add them via Hydra overrides.

## Run the full pipeline

```bash
cd examples

uv run aereo action=run \
  +search._target_=aereo.builtins.search.search_stac \
  +search.stac_api_url="https://earth-search.aws.element84.com/v1" \
  +search.collections.sentinel-2-l2a="[red, nir]" \
  geojson=config/aoi/chocon.geojson \
  start="2024-01-01T00:00:00Z" \
  end="2024-01-10T23:59:59Z" \
  +read._target_=aereo.builtins.read.read_odc_stac \
  +write._target_=aereo.builtins.write.write_geotiff
```

`action=run` performs search, build-tasks, and execute in one command.

## Individual stages

```bash
# Search only
uv run aereo action=search \
  +search._target_=aereo.builtins.search.search_stac \
  +search.stac_api_url="https://earth-search.aws.element84.com/v1" \
  +search.collections.sentinel-2-l2a="[red, nir]" \
  geojson=config/aoi/chocon.geojson \
  start="2024-01-01T00:00:00Z" \
  end="2024-01-10T23:59:59Z"

# Build tasks from saved search results
uv run aereo action=build-tasks \
  search_results=out/search_results.json \
  +read._target_=aereo.builtins.read.read_odc_stac \
  +write._target_=aereo.builtins.write.write_geotiff

# Extract from saved tasks
uv run aereo action=extract \
  tasks=out/tasks.pkl \
  +read._target_=aereo.builtins.read.read_odc_stac \
  +write._target_=aereo.builtins.write.write_geotiff

# Validate a config without network calls
uv run aereo action=validate \
  +search._target_=aereo.builtins.search.search_stac \
  +read._target_=aereo.builtins.read.read_odc_stac \
  +write._target_=aereo.builtins.write.write_geotiff
```

## Discover plugins

```bash
# List installed plugins
uv run aereo action=plugins

# Show parameters for a plugin
uv run aereo action=plugin_params plugin=search_stac
```

## Override config values

Hydra-style overrides work on the command line:

```bash
uv run aereo action=run \
  +search._target_=aereo.builtins.search.search_stac \
  grid_dist=10000 \
  target_aoi=config/aoi/cordoba.geojson \
  +read._target_=aereo.builtins.read.read_odc_stac \
  +write._target_=aereo.builtins.write.write_geotiff
```

Use `+` when the key does not already exist in the default CLI config.
