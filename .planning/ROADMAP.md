# Roadmap: aer Plugin Extraction System

## Overview

**3 phases** | **11 requirements mapped** | All v1 requirements covered ✓

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|-----------------|
| 1 | Extract Plugin System | Define extract plugin interface and registry | EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05 | 5 |
| 2 | Pipeline Integration | Integrate extract into aer-core pipeline | PIPE-01, PIPE-02, PIPE-03 | 4 |
| 3 | Example Plugin | Implement aws-goes-extract as reference | AWSG-01, AWSG-02, AWSG-03 | 4 |

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

## Phase Summary

| Phase | Focus | Key Deliverable |
|-------|-------|-----------------|
| 1 | Interface | ExtractPlugin protocol + registry |
| 2 | Orchestration | Pipeline search → extract |
| 3 | Example | aws-goes-extract reference impl |
| 4 | Grid Refactor | Multi-grid SearchResult support |

---

*Roadmap updated: 2026-03-27*
