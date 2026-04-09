# Roadmap: aer Plugin Extraction System

## Overview

**6 phases** | **20 requirements mapped** | All v1 requirements covered ✓

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|-----------------|
| 1 | Extract Plugin System | Define extract plugin interface and registry | EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05 | 5 |
| 2 | Pipeline Integration | Integrate extract into aer-core pipeline | PIPE-01, PIPE-02, PIPE-03 | 4 |
| 3 | Example Plugin | Implement aws-goes-extract as reference | AWSG-01, AWSG-02, AWSG-03 | 4 |
| 5 | Adapt Search Plugins to Pluggy | Migrate aer-search-aws-goes and aer-search-earthaccess to new pluggy hookimpl system | PLUG-01, PLUG-02, PLUG-03, PLUG-04 | 4 |
| 6 | Product-Based Plugin Dispatch | Auto-select plugins based on product support | PROD-01, PROD-02, PROD-03, PROD-04, PROD-05 | 5 |

---

## Phase 1: Extract Plugin System

**Goal:** Define the extract plugin interface and registry pattern in aer-core.

**Requirements:**
- EXTR-01: Extract plugin receives SearchResultSchema GeoDataFrame as input
- EXTR-02: Extract plugin returns file paths (local disk or S3 URLs)
- EXTR-03: Extract plugin handles reprojection to majortom grid internally
- EXTR-04: User specifies target cells via GridSpatialExtent
- EXTR-05: Extract plugins registered via entry points in pyproject.toml

**Success Criteria:**
1. `ExtractPlugin` protocol defined in `aer.plugin` or new component
2. Entry point group `aer.plugins.extract` configured
3. Extract plugin can be registered with `@plugin(name=..., category="extract")`
4. Bootstrap discovers extract plugins alongside search plugins
5. Example: plugin can be loaded via `PluginRegistry.get("aws-goes", "extract")`

**Artifacts:**
- New component: `components/aer/extract/` with interface and schema

---

## Phase 2: Pipeline Integration

**Goal:** Integrate extract into aer-core to orchestrate search → extract flow.

**Requirements:**
- PIPE-01: Pipeline orchestrates search → extract flow
- PIPE-02: aer-core defines extract plugin interface
- PIPE-03: Bootstrap discovers extract plugins alongside search plugins

**Success Criteria:**
1. User can call `Pipeline().run(search_results, extract_plugin_name)`
2. Extract phase receives SearchResultSchema, returns extracted file paths
3. Integration tests pass with mock extract plugin
4. Documentation in README for search → extract workflow

**Artifacts:**
- Updated `aer.plugin` Pipeline to support extract category
- Updated `aer.bootstrap` for extract plugin discovery
- Integration tests in `test/integration/`

---

## Phase 3: Example Plugin

**Goal:** Implement aws-goes-extract as reference implementation.

**Requirements:**
- AWSG-01: aws-goes-extract plugin implemented
- AWSG-02: aws-goes-extract conforms to extract plugin interface
- AWSG-03: aws-goes-extract project with proper entry points

**Success Criteria:**
1. `projects/aer-extract-aws-goes/` created with pyproject.toml
2. Entry point `aer.plugins.extract.aws_goes = ...` registered
3. Plugin handles GOES band extraction and majortom reprojection
4. End-to-end test: search GOES → extract → verify output paths

**Artifacts:**
- New project: `projects/aer-extract-aws-goes/`
- Entry in root `pyproject.toml` for development discovery
- Unit and integration tests

---

---

## Phase 4: SearchResult Grid Refactor

**Goal:** Refactor SearchResult and ExtractionTask classes to support multiple GridRows per SearchResult, instead of exploding overlapping spatial extents into separate results.

**Requirements:**
- SGRD-01: SearchResult has list of GridRows (not single grid_cell)
- SGRD-02: ExtractionTask receives all overlapping grid_cells in one task
- SGRD-03: Search plugins updated to return multiple GridRows per result
- SGRD-04: Avoid duplicate extraction costs from overlapping cells

**Success Criteria:**
1. SearchResultSchema has `grid_rows: list[GridRow]` attribute
2. SearchResultSchema has computed grid_cells property returning all cells
3. ExtractionTask receives full list of GridRows from search results
4. Search plugins refactored to emit GridRows per spatial extent
5. Unit tests for multi-grid SearchResult scenarios

**Artifacts:**
- Updated SearchResultSchema with grid_rows list
- Updated ExtractionTask to accept multiple GridRows
- Refactored any search plugins that need updating
- Tests in components/aer/*/test/

---

## Phase 5: Adapt Search Plugins to Pluggy

**Goal:** Migrate repos/aer-search-aws-goes and repos/aer-search-earthaccess to the new pluggy-based plugin system defined in aer.plugin.core, removing deprecated @plugin decorator and Product types.

**Requirements:**
- PLUG-01: Search plugins use @hookimpl class pattern instead of @plugin decorator
- PLUG-02: Search plugins accept (collections, intersects, time_range, search_params) instead of SearchQuery with Product types
- PLUG-03: Search plugins return GeoDataFrame[SearchResultSchema] matching the new simplified schema (id, collection, geometry, start_time, end_time, href)
- PLUG-04: Entry points register class instances, not bare functions

**Success Criteria:**
1. Both plugins use class-based `@hookimpl` pattern conforming to `AerSpec.search()`
2. No imports of deprecated `Product`, `Channel`, `SearchQuery`, `GridSpatialExtent`, or `@plugin` decorator
3. Both return GeoDataFrame matching the new `SearchResultSchema` (id, collection, geometry, start_time, end_time, href)
4. Entry points in pyproject.toml register class instances

**Artifacts:**
- Updated `aer-search-aws-goes/components/aer/search_aws_goes/core.py`
- Updated `aer-search-earthaccess/components/aer/search_earthaccess/core.py`
- Updated tests in both repos
- Updated pyproject.toml entry points in both repos

---

## Phase Summary

| Phase | Focus | Key Deliverable |
|-------|-------|-----------------|
| 1 | Interface | ExtractPlugin protocol + registry |
| 2 | Orchestration | Pipeline search → extract |
| 3 | Example | aws-goes-extract reference impl |
| 4 | Grid Refactor | Multi-grid SearchResult support |
| 5 | Plugin Migration | Search plugins → pluggy hookimpl |
| 6 | Product Dispatch | Auto-select plugins by product |

---

## Phase 6: Product-Based Plugin Dispatch

**Goal:** Implement automatic plugin selection based on product support, with conflict resolution for multiple matching plugins.

**Requirements:**
- PROD-01: Plugin creators MUST specify supported products via required `supported_products` class attribute
- PROD-02: User declares products they want to use (not plugin names)
- PROD-03: System automatically dispatches to corresponding plugin based on product support
- PROD-04: When two plugins support same products: user can select by plugin name + warning shown
- PROD-05: Great UX - minimal friction for users

**Success Criteria:**
1. Plugins declare `supported_products: list[str]` class attribute (required)
2. `PluginSelector` class indexes plugins by product and selects based on user request
3. Single matching plugin → auto-selected (seamless UX)
4. Multiple matching plugins → raise `PluginConflictError` unless user specifies plugin_name
5. Zero matching plugins → raise `NoMatchingPluginError` with helpful message

**Artifacts:**
- Updated `components/aer/plugin/core.py` (Product type, helper functions)
- New `components/aer/plugin/selector.py` (PluginSelector class)
- Updated `components/aer/plugin/__init__.py` (exports)
- Updated `components/aer/plugin/api.py` (run_search with dispatch)

---

*Roadmap updated: 2026-04-06*
