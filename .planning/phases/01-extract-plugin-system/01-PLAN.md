---
description: "Create Extract Plugin Component and Protocol"
depends_on: []
wave: 1
autonomous: true
files_modified:
  - components/aer/extract/core.py
  - components/aer/extract/__init__.py
  - test/components/aer/extract/test_core.py
requirements:
  - EXTR-01
  - EXTR-02
  - EXTR-03
  - EXTR-04
  - EXTR-05
---

<objective>
To implement the extract plugin interface and registry pattern within the aer-core project by creating the `extract` Polylith component. This involves defining the `ExtractedResultSchema` and the `ExtractPlugin` protocol which will be used by external plugins.
</objective>

<task>
  <objective>Create the `extract` component using `poly-create` workflow</objective>
  <read_first>
    - .planning/phases/01-extract-plugin-system/01-CONTEXT.md
  </read_first>
  <action>
    Run the `/poly-create` workflow to create a new component `extract` in the `aer` namespace.
    As per the rules, invoke the workflow or execute `uv run poly create component --name extract` in the repository root.
  </action>
  <acceptance_criteria>
    - Directory `components/aer/extract` exists.
    - File `components/aer/extract/__init__.py` exists.
  </acceptance_criteria>
</task>

<task>
  <objective>Define `ExtractedResultSchema` and `ExtractPlugin` protocol</objective>
  <read_first>
    - components/aer/search/core.py
    - components/aer/spatial/core.py
    - .planning/phases/01-extract-plugin-system/01-CONTEXT.md
    - components/aer/extract/core.py
  </read_first>
  <action>
    In `components/aer/extract/core.py`, implement the following:
    1. Import `SearchResultSchema` from `aer.search.core` (or copy fields if Pandera inheritance issues arise, but ideally inherit or combine fields). You should define `ExtractedResultSchema(pa.DataFrameModel)`.
    2. Add fields to `ExtractedResultSchema`:
       - `reprojected_path: Series[pa.String] = pa.Field(nullable=False)`
       - `resolution: Series[float] = pa.Field(nullable=False)`
    3. Define `ExtractPlugin(Protocol)` class with the method:
       `def extract(self, gdf: GeoDataFrame[SearchResultSchema], grid_spatial_extent: GridSpatialExtent, output_dir: str, **options: Any) -> GeoDataFrame["ExtractedResultSchema"]:`
    4. Ensure necessary imports: `Any`, `typing.Protocol`, `pandera.typing.geopandas.GeoDataFrame`, `aer.spatial.GridSpatialExtent`, `aer.search.SearchResultSchema`, `pandera.typing.Series`, `pandera.pandas as pa`.
  </action>
  <acceptance_criteria>
    - `components/aer/extract/core.py` contains `class ExtractedResultSchema`
    - `components/aer/extract/core.py` contains `class ExtractPlugin(Protocol)`
    - `components/aer/extract/core.py` contains `def extract(self, gdf: GeoDataFrame`
  </acceptance_criteria>
</task>

<task>
  <objective>Export classes in the component</objective>
  <read_first>
    - components/aer/extract/__init__.py
  </read_first>
  <action>
    In `components/aer/extract/__init__.py`, import `ExtractedResultSchema` and `ExtractPlugin` from `.core` and add them to `__all__`.
    `from .core import ExtractedResultSchema, ExtractPlugin`
    `__all__ = ["ExtractedResultSchema", "ExtractPlugin"]`
  </action>
  <acceptance_criteria>
    - `components/aer/extract/__init__.py` contains `__all__ = ["ExtractedResultSchema", "ExtractPlugin"]`
  </acceptance_criteria>
</task>

<task>
  <objective>Write unit tests for the extract component</objective>
  <read_first>
    - test/components/aer/extract/test_core.py
  </read_first>
  <action>
    Create `test/components/aer/extract/test_core.py` (which might be created by `poly create`).
    Write a test `test_extracted_result_schema()` that validates a dummy GeoDataFrame against `ExtractedResultSchema`. (Mock necessary fields including `reprojected_path` and `resolution`).
    Write a test `test_extract_plugin_protocol()` verifying a dummy class implementing `ExtractPlugin` can be instantiated and type checked physically or logically.
  </action>
  <acceptance_criteria>
    - `test/components/aer/extract/test_core.py` contains `def test_extracted_result_schema`
    - Command `uv run pytest test/components/aer/extract/test_core.py` passes with exit code 0.
  </acceptance_criteria>
</task>

<verification>
<must_haves>
- ExtractPlugin protocol is defined and importable from `aer.extract`
- ExtractedResultSchema has `reprojected_path` and `resolution` fields alongside search result fields.
- Tests pass via `uv run pytest test/components/aer/extract/test_core.py`.
</must_haves>
<step>
Run `uv run pytest test/components/aer/extract/test_core.py` to ensure tests execute successfully.
</step>
</verification>
