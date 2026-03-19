---
description: "Create dummy extract plugin integration test"
depends_on: []
wave: 1
autonomous: true
files_modified:
  - test/components/aer/plugin/test_integration.py
requirements:
  - AWSG-01
  - AWSG-02
  - AWSG-03
---

<objective>
Create a dummy extract plugin as a test fixture and write an integration test that exercises the full search → extract flow via the public API (`run_search` → `run_extract`), validating the output conforms to `ExtractedResultSchema`.
</objective>

<task>
  <objective>Write integration test with dummy search + extract plugins</objective>
  <read_first>
    - components/aer/plugin/core.py
    - components/aer/extract/core.py
    - components/aer/search/core.py
    - test/components/aer/plugin/test_api.py
    - test/components/aer/extract/test_core.py
  </read_first>
  <action>
    Create `test/components/aer/plugin/test_integration.py` with:

    1. A `@plugin(name="dummy-search", category="search")` function that receives a SearchQuery-like object and returns a valid `SearchResultSchema` GeoDataFrame (use the same field pattern from `test_core.py`: product_name, granule_id, start_time, end_time, s3_url, https_url, size_mb, geometry, overlapping_spatial_extent, input_spatial_extent, cell_overlap_mode).

    2. A `@plugin(name="dummy-extract", category="extract")` function that receives a SearchResultSchema GeoDataFrame + output_dir, and returns a valid `ExtractedResultSchema` GeoDataFrame (copy input columns + add `reprojected_path` and `resolution`).

    3. `test_search_then_extract_integration()`:
       - Call `run_search("dummy-search", query_object)`
       - Call `run_extract("dummy-extract", search_results, "/tmp/test_output")`
       - Validate result with `ExtractedResultSchema.validate(result)`
       - Assert `reprojected_path` and `resolution` columns exist and have valid values.

    4. `test_extract_empty_gdf()`:
       - Call extract with an empty but schema-valid GeoDataFrame
       - Should return empty ExtractedResultSchema GeoDataFrame without error.

    Run with `uv run pytest test/components/aer/plugin/test_integration.py`.
  </action>
  <acceptance_criteria>
    - `test/components/aer/plugin/test_integration.py` contains `def test_search_then_extract_integration`
    - `test/components/aer/plugin/test_integration.py` contains `@plugin(name="dummy-extract", category="extract")`
    - Command `uv run pytest test/components/aer/plugin/test_integration.py` exits with code 0
  </acceptance_criteria>
</task>

<verification>
<must_haves>
- Dummy extract plugin conforms to ExtractPlugin protocol
- Integration test exercises run_search → run_extract end-to-end
- Output validated against ExtractedResultSchema
- Tests pass
</must_haves>
<step>
Run `uv run pytest test/components/aer/plugin/test_integration.py` to validate.
</step>
</verification>
