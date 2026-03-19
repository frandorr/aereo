# Phase 1: Extract Plugin System - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Define the extract plugin interface and registry pattern in aer-core. **Plugins live in separate external repositories** — this phase only defines what plugins implement against (interface, schema, entry points). Extract plugins receive SearchResultSchema GeoDataFrames, reproject data to majortom grid cells, and return extraction results as paths with metadata.

</domain>

<decisions>
## Implementation Decisions

### Plugin Interface
- Use the same `@plugin` decorator pattern as search plugins
- Function signature: `extract(gdf, grid_spatial_extent, output_dir, **options) -> GeoDataFrame[ExtractedResultSchema]`
- Plugins handle reprojection to majortom grid internally
- **Plugins are external** — aer-core defines the contract, external repos implement plugins

### Result Schema
- New `ExtractedResultSchema` (Pandera DataFrameModel) in new `components/aer/extract/` component
- Schema similar to SearchResultSchema with additional columns:
  - `reprojected_path`: Path to extracted/reprojected file (local or S3 URL)
  - `resolution`: Target resolution in meters
- Inherits columns from SearchResultSchema (granule_id, product_name, geometry, etc.)

### Return Value
- ExtractedResultSchema GeoDataFrame with comprehensive metadata:
  - Cell ID, file path, band info, resolution, output format, timestamp, file size
- Users know what they requested and where output files are stored

### Entry Point Naming
- `aer.plugins.extract` — parallel to `aer.plugins.search`
- Plugins register with category `"extract"`

### New Component Structure
- `components/aer/extract/`
  - `core.py`: ExtractedResultSchema, extract plugin utilities
  - `__init__.py`: Public exports via `__all__`

</decisions>

<canonical_refs>
## Canonical References

### Plugin System
- `components/aer/plugin/core.py` — Existing @plugin decorator, PluginRegistry, Pipeline
- `components/aer/search/core.py` — SearchResultSchema pattern to mirror

### Spatial Domain
- `components/aer/spatial/core.py` — GridSpatialExtent, GridCell for cell specification
- `components/aer/temporal/core.py` — TimeRange

### Existing Architecture
- `.planning/codebase/ARCHITECTURE.md` — Polylith structure, plugin system design
- `.planning/codebase/STRUCTURE.md` — Component conventions

### Project Context
- `.planning/PROJECT.md` — Core value and constraints
- `.planning/REQUIREMENTS.md` — Phase 1 requirements (EXTR-01 through EXTR-05)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `@plugin` decorator: Can reuse directly for extract plugins
- `PluginRegistry`: Already supports multiple categories — extract just needs new category
- `Pipeline`: Can chain search → extract workflow

### Established Patterns
- SearchResultSchema: Template for ExtractedResultSchema
- attrs.frozen: Use for immutable data classes
- Pandera DataFrameModel: Schema validation pattern

### Integration Points
- Bootstrap (`aer.bootstrap`): Discover extract plugins alongside search
- New extract component: Imports from spatial, temporal, spectral components
- Root pyproject.toml: Add entry point for development discovery

</code_context>

<deferred>
## Deferred Ideas

- **Phase 3 (aws-goes-extract) scope change needed** — This phase was planned as example plugin implementation, but plugins live in external repositories. Either remove Phase 3 or reframe as "plugin implementation guide" / "example plugin template"

</deferred>

---

*Phase: 01-extract-plugin-system*
*Context gathered: 2026-03-19*
