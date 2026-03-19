# Phase 3: Example Plugin - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Create a dummy/mock extract plugin as a test fixture to validate the full search → extract flow end-to-end. **No real plugin implementation** — real plugins (like aws-goes-extract) live in separate external repos. This phase proves the interface works by exercising `@plugin`, `run_search`, `run_extract`, and schema validation with a fake plugin.

</domain>

<decisions>
## Implementation Decisions

### No Real Plugin
- Real extract plugins live in separate external repos — NOT in this monorepo
- This phase creates a **test-only** dummy plugin to validate the integration
- No new Polylith project needed

### Dummy Plugin Scope
- A mock extract plugin registered with `@plugin(name="dummy", category="extract")`
- Receives a SearchResultSchema GeoDataFrame, returns an ExtractedResultSchema GeoDataFrame
- Does NOT do real reprojection or file I/O — just transforms the input into the expected output schema
- Lives in the test directory, not in components/

### Integration Test
- End-to-end test: register dummy search + dummy extract → call `run_search` → call `run_extract` → validate output conforms to `ExtractedResultSchema`
- Proves the full contract works

### Claude's Discretion
- Exact test file location and structure
- Whether to include the dummy plugin as a pytest fixture or module-level registration
- Additional edge case tests (empty GeoDataFrame, missing columns, etc.)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Plugin System
- `components/aer/plugin/core.py` — `@plugin`, `run_search`, `run_extract`, PluginRegistry
- `components/aer/extract/core.py` — ExtractedResultSchema, ExtractPlugin protocol
- `components/aer/search/core.py` — SearchResultSchema, SearchQuery, SearchPlugin protocol

### Existing Tests
- `test/components/aer/plugin/test_api.py` — Existing tests for run_search/run_extract
- `test/components/aer/extract/test_core.py` — Existing schema validation tests

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `test/components/aer/plugin/test_api.py` already has mock search + extract plugins (simple dict-returning)
- `test/components/aer/extract/test_core.py` already builds a valid ExtractedResultSchema GeoDataFrame

### Established Patterns
- Pandera schema validation via `ExtractedResultSchema.validate(gdf)`
- `@plugin(name, category)` decorator for registration

### Integration Points
- `run_search` + `run_extract` from `aer.plugin` — the public API to test

</code_context>

<specifics>
## Specific Ideas

- The dummy plugin should produce a valid ExtractedResultSchema GeoDataFrame so the schema validation test is meaningful

</specifics>

<deferred>
## Deferred Ideas

- Real aws-goes-extract plugin — separate repo
- Plugin implementation guide / template documentation — future work

</deferred>

---

*Phase: 03-example-plugin*
*Context gathered: 2026-03-19*
