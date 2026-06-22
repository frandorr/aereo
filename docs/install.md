# Install

Pick your sensor and copy-paste the install command.

## Core

```bash
pip install aereo
```

This gives you the `AereoClient`, the Hydra CLI, the built-in stage plugins
(`ReadODCSTAC`, `ReprojectODC`, `WriteGeoTIFF`, `NDVI`, `SelectBands`, ...), and
grid utilities. You can search public STAC catalogs and extract with ODC-STAC
using only the core package.

## Sensor-specific setups

Most search and I/O plugins live in separate packages. Install the ones that
match your data source.

### Sentinel-2 (Planetary Computer)

```bash
pip install aereo aereo-search-planetary-computer
```

Required credentials: a [Planetary Computer subscription key](https://planetarycomputer.microsoft.com/docs/concepts/sas/)
is recommended for signed assets. The built-in `SearchSTAC` config in
`examples/config/search/sentinel2_pc.yaml` shows how to use
`planetary_computer.sign_inplace`.

### MODIS / VIIRS / Sentinel-3 (NASA Earthdata)

```bash
pip install aereo aereo-search-earthaccess
```

Required credentials: NASA Earthdata login. Set them via environment variables
(`EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD`) or a `~/.netrc` file. See
[Earthdata Login](https://urs.earthdata.nasa.gov/) and the
[earthaccess docs](https://earthaccess.readthedocs.io/en/latest/howto/authenticate/).

### GOES ABI (public AWS S3, no auth)

```bash
pip install aereo aereo-search-aws-goes
```

No credentials needed for search. If you also want to read GOES with Satpy,
install the corresponding reader plugin:

```bash
pip install aereo-read-satpy
```

### Satpy-based readers / reprojectors

```bash
pip install aereo-read-satpy aereo-reproject-satpy
```

Use these when your pipeline stages use `ReadSatpy` or `ReprojectSatpy` instead
of the built-in ODC-STAC stages.

### Tessera

```bash
pip install aereo aereo-search-tessera aereo-read-tessera
```

---

## Verify the installation

List every plugin AEREO can discover:

```bash
aereo action=plugins
```

You should see built-in plugins (`SearchSTAC`, `ReadODCSTAC`, ...) plus any
sensor-specific plugins you installed. To inspect a single plugin's parameters:

```bash
aereo action=plugin_params plugin_name=SearchSTAC
```

---

## Troubleshooting

### `PluginNotFoundError: No search plugin found for collection ...`

AEREO is a plugin-based framework. Installing only `aereo` gives you the core
client and interfaces, but you need at least one search plugin and one reader
plugin to run a pipeline.

**Fix:** Install the plugins for your sensor (see commands above) and verify:

```bash
aereo action=plugins
```

If a plugin is missing, install the corresponding pip package and run the
command again. The package must be installed in the same environment as `aereo`:

```bash
python -c "import aereo_search_aws_goes"
```

If this raises `ModuleNotFoundError`, install the package.

### Old docs mention `aereo-extract-satpy` or `aereo-extract-odc-stac`

Those package names are outdated. The current plugin packages are named
`aereo-search-*`, `aereo-read-*`, and `aereo-reproject-*`. If you are following
an old blog post or notebook, replace `aereo-extract-satpy` with
`aereo-read-satpy` (and add `aereo-reproject-satpy` if the pipeline reprojects
with Satpy).
