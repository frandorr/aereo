# Changelog

## 1.4.2 (2026-08-07)

- Fix `plot_artifact_patches` regression from 1.4.1: unifying mixed-UTM
  footprints assigned a plain list to `cell_utm_footprint`, downgrading it
  to a pandas Series without `total_bounds` whenever the GeoDataFrame's
  active geometry was another column (as in the real artifact catalog).
  Footprints are now assigned as a `GeoSeries`.

## 1.4.1 (2026-08-07)

- Fix `plot_artifact_patches` for AOIs near a UTM zone boundary: grid-cell
  footprints expressed in different UTM zones are reprojected to the first
  artifact's `cell_utm_crs` before plotting, so out-of-zone cells no longer
  render far off their true position or stretch the axis limits. The AOI
  overlay uses the same target CRS for consistency.

## 1.4.0 (2026-08-07)

- Add opt-in UTM inference for `reproject_mode="raw"` via the `crs: "utm"`
  sentinel. The orchestrator infers the UTM EPSG from the dataset footprint
  after read and preprocess, then passes the concrete CRS to the reprojector.
- Fail fast when `reproject_mode="raw"` is used without a configured `crs`:
  `ExtractionJob` validation catches missing `crs` on `functools.partial`
  reprojectors, and `run_task` raises the same actionable error for
  non-partial callables that do not accept a `crs` argument.
- Reclaim retained memory in `LocalExecutor.shutdown`: run `gc.collect()` +
  `malloc_trim(0)` for the current process and terminate joblib's reusable
  loky pool, so RSS drops after a batch completes. Only applies when the
  executor actually dispatched parallel work, and never for the threading
  backend.
- Resolve relative geometry paths (`.geojson`/`.json`) in job configs against
  the job config directory instead of only the process CWD, so loading a job
  from a notebook or another directory no longer fails with
  `Geometry file not found` when the file sits next to the job YAML.

## 1.3.0 (2026-08-06)

- Rename the top-level `ExtractionJob.resolution` field to `grid_resolution` to disambiguate it from the `resolution` keyword bound inside the `reproject:` block (used by reprojection plugins to self-construct a target GeoBox in `reproject_mode="raw"`). The legacy `resolution` key is still accepted as an alias, and older serialized task payloads are read with a fallback, so existing configs keep working.
- Update example configs, tutorial notebooks, and docs to use `grid_resolution`.

## 1.2.3 (2026-07-30)

- Warn when `LocalExecutor` is created with `use_threads=True` and parallel workers: the threading backend shares native library state and can deadlock or hang when reading formats like netCDF/HDF5 (`.nc`). The default process-based backend (cores) is recommended instead.

## 1.2.2 (2026-07-28)

- Fix `reproject_odc` in raw mode (no geobox): warp the source bounds into the target CRS before building the target geobox, instead of passing EPSG:4326 degree bounds as metres — previously the output collapsed to a 1x1 pixel and jobs produced empty artifacts.
- Accept bare EPSG number strings (e.g. `"32720"`) as the target `crs` in `reproject_odc`.

## 1.2.1 (2026-07-21)

- Fix `GridCell.to_geobox` for non-integer and sub-metre resolutions (e.g. MODIS, < 1 m).
- Lazy-import `pystac_client` to speed up config loading.
- Refresh README layout, onboarding, and examples gallery.
- Remove references to retired `aereo-lambda` and `aereo-extract` projects from docs.
- Update tutorial notebooks with Colab badges and Earthdata authentication notes.

## 1.2.0 (2026-07-09)

- Add `pc` optional extra for Microsoft Planetary Computer support (`uv add "aereo[pc]"`).
- Add Planetary Computer Sentinel-2 example (`examples/planetary_computer_s2.py`) and config.
- Refresh README: move quick install before examples, add VIIRS vs GOES-19 ABI comparison gallery.
- Add NASA Earthdata authentication disclaimers to README and to VIIRS/Sentinel-3/Multiple-constellation notebooks.
- Add Colab badges to the docs examples index.

## 1.1.5 (2026-07-09)

- Fix readers: pre-initialize `odc.loader` GDAL/rasterio session to avoid deadlock.
- Docs: add Colab badges and per-notebook setup cells to tutorial notebooks.

## 1.1.4 (2026-07-09)

- Remove the `aereo-extract` runtime project from the workspace.
- Add `pyarrow` to core dependencies.
- Update example configs and packaging metadata.

## 1.1.3 (2026-07-08)

Major refactor to a function-based, job-centric API:

- Replace class-based plugins with plain `@validate_call` functions discovered via entry points.
- Introduce `ExtractionJob` orchestration: `search`, `build_tasks`, `execute`, `write_catalog`.
- Replace legacy backends with `LocalExecutor` and `LambdaExecutor` in `aereo.executors`.
- Add `aereo.backends` with task staging and S3/FS storage.
- New swath reprojection implementation using `pyresample` (`reproject_pyresample`).
- Add `grid_cells_margin`, `cells_per_task`, per-task AOI clipping, and single-CRS `ExtractionTask` enforcement.
- Add `download_assets`, NDWI/NDVI processors, `plot_artifact_patches` visualization helpers.
- Add per-task artifact cache with `TaskResultCache`.
- Add Hydra-native config loading via `ExtractionJob.load_from_config`.
- New tutorial notebooks: Sentinel-2 NDVI/NDWI, VIIRS, Sentinel-3 OLCI, GOES-19 ABI, GeoTessera, Multiple constellations.
- Document optional extras (`serverless`, `swath`, `viz`, `all`).
- Rebuild documentation site with MkDocs Material.

## 1.1.1 (2026-05-26)

- Fix packaging metadata and restore EOIDS path generation in core.
- Add missing runtime dependencies (`pyproj`, `requests`, `filelock`, `rasterio`, `numpy`).
- Update CI to install only the `aereo` project and skip plugin-dependent tests when plugins are absent.

## 1.1.0 (2026-05-26)

- Rebrand all `Aer*` classes and modules to `Aereo*`.
- Add `PluginParam` metadata to `AereoPlugin` and `AereoRegistry` for richer plugin introspection.
- Remove forced GDAL auto-configuration.
- Fix stale class/repository references across README, docs, examples, and smoke tests.
- Packaging fix: include `gdal_env.py` in the wheel via force-include.

## 1.0.2 (2026-05-24)

- Initial stable release.
- Supported sensors: GOES ABI, Sentinel-2 MSI, MODIS, VIIRS, Sentinel-3 OLCI.
- Plugin-based search/extract architecture with entry-point discovery.
- Major TOM grid alignment.
- CLI: `aereo run`, `aereo plugins`, `aereo validate`.

## v1.0.1 (2026-05-07)

### Chores

- Rename pypi package from aer-core to aereo
  ([`dac8a8e`](https://github.com/frandorr/aereo/commit/dac8a8edb16494d2b67391a0496c4a984b89b247))


## v1.0.0 (2026-05-07)

- Initial Release
