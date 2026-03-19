# aer Plugin Extraction System

## What This Is

A plugin-based extraction pipeline for satellite data that standardizes how data is extracted and reprojected to the majortom grid. Independent of satellite source — search and extract plugins conform to aer-core interfaces.

## Core Value

Users can search data from any satellite provider and extract it to a standardized grid in a consistent way, regardless of source.

## Requirements

### Validated

- ✓ Search plugin system — entry point discovery, registry pattern
- ✓ Spatial component — GridSpatialExtent, GridCell, majortom grid
- ✓ Temporal component — TimeRange for temporal queries
- ✓ Spectral component — Instrument, Satellite, Band, Channel, Product registries

### Active

- [ ] Extract plugin system — parallel to search, same discovery pattern
- [ ] Extract plugin interface — receives SearchResultSchema, returns file paths
- [ ] Pipeline integration — orchestrate search → extract flow
- [ ] Example extract plugin (aws-goes-extract)

### Out of Scope

- [Direct data processing after extraction] — users own their extracted data
- [Multi-band fusion] — each plugin handles its own bands
- [Built-in visualization] — out of scope for extraction pipeline

## Context

aer uses Polylith architecture with components/bases/projects. The plugin system uses entry points registered in `pyproject.toml` and discovered via `importlib.metadata`. Existing components:

- `components/aer/spatial/` — GridSpatialExtent, GridCell, majortom grid definitions
- `components/aer/search/` — SearchResultSchema, SearchQuery
- `components/aer/spectral/` — Instrument, Satellite, Band, Channel, Product
- `components/aer/temporal/` — TimeRange
- `components/aer/plugin/` — PluginRegistry, Pipeline, @plugin decorator
- `components/aer/bootstrap/` — Plugin discovery bootstrap
- `bases/aer/download_api/` — Download orchestrator

Extraction mirrors the search plugin pattern but for data extraction and reprojection.

## Constraints

- **Interface**: Extract plugins must conform to aer-core interfaces (spatial, temporal)
- **Grid system**: Majortom grid defined in spatial component
- **Output format**: Plugin-defined (zarr, geotiff, etc.) — returned as paths (local or S3)
- **Python**: 3.13+ only

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Extract plugins use entry points | Consistent with search plugin discovery | — Pending |
| Reprojection handled by plugin | Different satellites need different reprojection logic | — Pending |
| Output as paths | Flexible — disk or S3, user decides | — Pending |

---
*Last updated: 2026-03-19 after initialization*
