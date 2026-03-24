# Quick Task 260324-wyj: check failing tests - Summary

## Goal
Fix failing tests in `aer-downloader-raw` and `aer-plugin` tests.

## Changes
1. Added required fields `cell_row`, `cell_col`, `cell_dist`, `cell_epsg`, `cell_bounds`, `channel_name` to the dummy `GeoDataFrame` in `test/components/aer/downloader_raw/test_core.py` and imported `shapely.geometry.Polygon` to fix testing dummy logic.
2. Updated `test/integration/test_plugins.py` to check for `'dummy-search'` rather than `'earthaccess'` since `earthaccess` plugin is optional and usually absent in dev installation.

## Outcome
All tests (94 items) pass locally via `uv run pytest`.
