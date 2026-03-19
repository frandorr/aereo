# Phase 2: Pipeline Integration - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Create a public API for the search → extract workflow. No Pipeline class involvement — just a simple, callable API that runs a search plugin then an extract plugin. This API is the foundation for future CLI and config-driven (Hydra-style) interfaces.

</domain>

<decisions>
## Implementation Decisions

### Public API Design
- Simple function-based API, not Pipeline-based
- User calls search plugin, gets GeoDataFrame, then calls extract plugin
- Could be a single orchestrator function like `run(search_plugin, extract_plugin, query, output_dir)` or composed from individual calls
- This is the public interface — later a CLI or Hydra config can call this same API

### No Pipeline Class Changes
- The existing `Pipeline` class is untouched in this phase
- Extract is wired through the public API, not through Pipeline chaining

### Bootstrap Discovery
- Bootstrap must discover extract plugins alongside search plugins
- Extract plugins register under `aer.plugins` entry point group with category `"extract"` (the existing PluginRegistry already supports multiple categories)

### Claude's Discretion
- Exact function signature and module location for the public API
- Whether the API is a single function or a small class
- Error handling patterns (what happens when search returns empty, extract fails, etc.)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Plugin System
- `components/aer/plugin/core.py` — PluginRegistry, @plugin decorator, Pipeline (existing, not modified)
- `components/aer/plugin/__init__.py` — Public exports

### Extract Interface (Phase 1 output)
- `components/aer/extract/core.py` — ExtractedResultSchema, ExtractPlugin protocol
- `components/aer/search/core.py` — SearchResultSchema, SearchQuery, SearchPlugin protocol

### Bootstrap
- `components/aer/bootstrap/core.py` — Current bootstrap() function

### Architecture
- `.planning/codebase/ARCHITECTURE.md` — Polylith structure
- `.planning/codebase/STRUCTURE.md` — Component conventions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PluginRegistry.get(name, category)` — Already supports fetching by name+category
- `plugin_registry.all()` — Bootstrap loads all `aer.plugins` entry points
- `SearchQuery` — Existing query object for search plugins
- `ExtractPlugin.extract(gdf, output_dir, **options)` — Phase 1 protocol

### Established Patterns
- `@plugin(name, category)` decorator for registration
- Pandera DataFrameModel for schema validation
- `SearchPlugin(Protocol)` pattern — mirrors ExtractPlugin

### Integration Points
- Bootstrap needs no changes if extract plugins register under `aer.plugins` group
- Public API lives in a new base or component (Claude's discretion)
- Entry point in project pyproject.toml for extract plugin discovery

</code_context>

<specifics>
## Specific Ideas

- The public API should be the single entry point that future CLIs and Hydra configs call into
- Keep it simple — a function you can call from a notebook or script

</specifics>

<deferred>
## Deferred Ideas

- CLI interface for the API — future phase
- Hydra/config-file driven invocation — future phase
- Pipeline class integration — deferred, may not be needed

</deferred>

---

*Phase: 02-pipeline-integration*
*Context gathered: 2026-03-19*
