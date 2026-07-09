# Changelog

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
