# PRD: AER Documentation Restructure — Search, Prepare, Extract-First UX

## 1. Problem Statement

### 1.1 Getting Started fails to guide new users

The current Getting Started experience is split between `quickstart.md` (57 lines, broken) and `installation.md` (148 lines, overwhelming). `quickstart.md` references an undefined `aoi_geometry` variable, causing a `NameError` on copy-paste. `installation.md` mixes user installation, per-sensor plugin setup, Earthdata auth, and developer Polylith workspace setup into one page — burying the 5-minute path under detail most users do not need.

### 1.2 The core Search / Prepare / Extract API lacks narrative focus

AER's entire user experience is built around three public client methods: `search()`, `prepare_for_extraction()`, and `extract_batches()`. Yet these are only documented deeply in `pipeline-architecture.md` (344 lines, UML diagrams, schema tables) — a technical reference that overwhelms new users. There is no concise, user-facing guide that walks through each phase with practical examples and common patterns.

### 1.3 Grid concepts are under-documented

`docs/grid.md` is 37 lines and omits `GridDefinition`, `target_grid_dist`, overlap options, and filtering modes. These concepts exist only in `examples/README.md` and an orphaned Jupyter notebook (`examples/grid/grid_filter_modes_demo.ipynb`), leaving users to discover them by accident.

### 1.4 Build and maintenance issues degrade trust

- `mkdocs build --strict` fails due to orphaned files and Griffe docstring warnings.
- `quickstart.md` has an undefined variable.
- `build-your-own-plugin.md` contains a YAML format error.
- `contributing.md` has a placeholder clone URL.
- `README.md` and `docs/index.md` have diverged, creating a maintenance burden.

## 2. Solution Overview

1. **Restructure Getting Started** into two focused pages:
   - `quickstart.md` — A narrative, step-by-step walkthrough of Search → Prepare → Extract with markdown explanations between code cells. Uses the same GOES-19 example as `index.md` for continuity.
   - `using-plugins.md` — Renamed from `installation.md`, trimmed to user-facing install commands, per-sensor plugin combinations, and Earthdata auth. Developer setup moves to `contributing/dev-setup.md`.

2. **Create a unified user guide for the pipeline**:
   - `pipeline.md` — One page with H2 sections for Search, Prepare, and Extract. Focuses on "what do I type and why," with common patterns, return-value inspection, and gotchas. Cross-links to `pipeline-architecture.md` for deep internals.

3. **Expand Grid documentation**:
   - Add `GridDefinition`, filtering modes (`intersection`, `within`, `coverage`), and overlap concepts to `grid.md`, with a link to the interactive notebook.

4. **Improve the homepage**:
   - Add a 5-line tl;dr at the top of `index.md`.
   - Add a simple Mermaid architecture diagram.
   - Rephrase the tagline to emphasize Major TOM grid readiness.
   - Update the documentation table to reflect the new nav.

5. **Fix build-breaking and trust issues**:
   - Fix all copy-paste bugs, YAML errors, and placeholder URLs.
   - Remove `last_session.md` from published docs.
   - Sync `README.md` as a subset of `index.md`.
   - Fix `mkdocs build --strict` failures.

6. **Add human-written context to API reference**:
   - Add a short intro to `docs/api/client.md` before the auto-generated `::: aer.client` block.

## 3. Specification

### 3.1 Navigation Structure (`mkdocs.yml`)

```yaml
nav:
  - Home: index.md
  - Getting Started:
    - Quick Start: quickstart.md
    - Running the Pipeline: pipeline.md
    - Using Plugins: using-plugins.md
  - Core Concepts:
    - Pipeline Architecture: pipeline-architecture.md
    - Grid System: grid.md
    - EOIDS: eoids.md
    - Plugins: plugins.md
  - Building Plugins:
    - Build Your Own Plugin: build-your-own-plugin.md
  - Contributing:
    - Guidelines: contributing.md
    - Developer Setup: contributing/dev-setup.md
  - API Reference:
    - Client: api/client.md
    - ... (remaining stubs)
```

### 3.2 Content Split Rules

| Topic | Page | Depth |
|-------|------|-------|
| Install core + plugins + Earthdata auth | `using-plugins.md` | Copy-paste commands only |
| Plugin discovery, interfaces, `plugin_hints` | `plugins.md` | Conceptual overview |
| Polylith, `uv sync`, dev environment | `contributing/dev-setup.md` | Step-by-step for contributors |
| Search parameters, sequence diagrams, schemas | `pipeline-architecture.md` | Deep technical reference |
| "How do I use `search()`?" | `pipeline.md` § Search | Practical guide |
| "How do I use `prepare_for_extraction()`?" | `pipeline.md` § Prepare | Practical guide |
| "How do I use `extract_batches()`?" | `pipeline.md` § Extract | Practical guide |

### 3.3 Quick Start Page Structure

```markdown
# Quick Start

## Before You Begin
Install AER and the GOES plugins:
```bash
pip install aer-eo aer-search-aws-goes aer-extract-satpy
```

## Step 1: Search
Explain: find granules matching time, AOI, and profile.
```python
# runnable snippet with imports and aoi defined
```

## Step 2: Prepare
Explain: turn search results into extraction tasks, grid is auto-selected.
Briefly mention `target_grid_dist`, `target_grid_overlap`, link to Grid docs.
```python
# runnable snippet continuing from Step 1
```

## Step 3: Extract
Explain: run extraction, get analysis-ready artifacts.
```python
# runnable snippet continuing from Step 2
```

## Next Steps
Link to Running the Pipeline, Grid System, Plugins.
```

### 3.4 Running the Pipeline Page Structure

```markdown
# Running the Pipeline

## Search
- Purpose sentence
- Minimal isolated example
- Key parameters table (profiles, intersects, start/end, search_params)
- Common pattern: searching multiple collections
- Return value inspection (GeoDataFrame columns)
- Gotcha: BEST_EFFORT vs STRICT

## Prepare
- Purpose sentence
- Minimal isolated example
- Key parameters (target_aoi, uri, profiles, target_grid_dist, target_grid_overlap)
- The two outputs: ExtractionTask objects and file mapping
- Common pattern: preparing multiple profiles at once
- Gotcha: `target_grid_dist` is cell size in meters, profile `resolution` is pixel size
- Cross-link to Grid docs for filter modes

## Extract
- Purpose sentence
- Minimal isolated example
- Key parameters (max_batch_workers, extract_params)
- Return value: ArtifactSchema GeoDataFrame columns
- Common pattern: extracting to EOIDS and mosaicking
- Gotcha: plugin-specific errors surface here
```

### 3.5 Grid Filtering Modes

Three modes are accepted inside `prepare_params`:

- `intersection` (default) — Keeps any cell touching asset geometry. Maximises coverage; may include mostly-NaN cells.
- `within` — Keeps only cells fully contained inside asset geometry. Conservative; avoids edge effects.
- `coverage` — Keeps cells where overlap fraction ≥ `min_coverage` (0.0–1.0). Tunable balance.

```python
client.prepare_for_extraction(
    ...,
    prepare_params={
        "grid_filter_mode": "coverage",
        "min_coverage": 0.5,
        "cells_per_chunk": 10,
    },
)
```

### 3.6 Mermaid Diagram for `index.md`

```mermaid
graph LR
    A[Search] --> B[Prepare]
    B --> C[Extract]
    C --> D[EOIDS Output]
```

## 4. Task Breakdown

### Phase 1 — Core (`aer` repo)

#### Task 1.1: Fix Griffe docstring warnings ✅ DONE
**File:** `components/aer/eoids/core.py`, `components/aer/grid/core.py`
**Action:** Add missing type annotations for `resolution` parameter and `**geobox_kwargs` to eliminate `mkdocs build --strict` Griffe warnings.

**Tests:**
```python
# No pytest test needed; verify with:
# mkdocs build --strict
# Should exit 0 with no warnings.
```

**Result:**
- Removed stray `resolution` docstring parameter from `build_eoids_path` (parameter did not exist in signature).
- Added `Any` type annotation to `**geobox_kwargs` in `GridDefinition.max_shape`.
- `mkdocs build --strict` now passes with zero Griffe warnings.
- `pytest test/components/aer/grid/ test/components/aer/eoids/` — 53 passed.
- `basedpyright components/aer/grid/core.py components/aer/eoids/core.py` — 0 errors, 0 warnings, 0 notes.

#### Task 1.2: Exclude `includes/abbreviations.md` from nav strict-check ✅ DONE
**File:** `mkdocs.yml`
**Action:** Add `not_in_nav` config so `--strict` does not flag the auto-included snippet file.

**Result:**
- Added `not_in_nav: | includes/abbreviations.md` to `mkdocs.yml`.
- `mkdocs build --strict` no longer lists `includes/abbreviations.md` as an omitted file.
- `pytest test/components/aer/grid/ test/components/aer/eoids/` — 53 passed.
- `basedpyright components/aer/grid/core.py components/aer/eoids/core.py` — 0 errors, 0 warnings, 0 notes.

### Phase 4 — Examples & Documentation

#### Task 4.1: Rewrite `docs/quickstart.md` ✅ DONE
**File:** `docs/quickstart.md`
**Action:**
- Start with inline install block.
- Build a step-by-step GOES-19 narrative with markdown explanations between code cells.
- Define `aoi` explicitly using `shapely.geometry.box`.
- Each step shows imports, code, and 1–2 sentences explaining what just happened.
- Briefly explain `target_grid_dist` / `target_grid_overlap` in Prepare, linking to Grid docs.
- End with "Next Steps" linking to `pipeline.md`, `grid.md`, `plugins.md`.

**Verification:**
```bash
# Copy-paste the entire quickstart into a fresh Python environment
# It should run without NameError and produce EOIDS output.
```

**Result:**
- Rewrote `docs/quickstart.md` as a three-step narrative (Search → Prepare → Extract).
- `aoi` is now explicitly defined with `shapely.geometry.box`.
- Added inline install block at the top.
- Added 1–2 sentence explanations between each code cell.
- Added brief `target_grid_dist` / `target_grid_overlap` explanation with link to Grid docs.
- Created stub `docs/pipeline.md` and `docs/using-plugins.md` so cross-links resolve and `mkdocs build --strict` passes.
- `pytest test/components/aer/grid/ test/components/aer/eoids/` — 53 passed.
- `mkdocs build --strict` — 0 warnings.

#### Task 4.2: Create `docs/using-plugins.md` ✅ DONE
**File:** `docs/using-plugins.md`
**Action:**
- Rename from `installation.md`.
- Keep only:
  1. `pip install aer-eo`
  2. Plugin combinations table (GOES, Sentinel-2, MODIS/VIIRS) with copy-paste commands
  3. `AerRegistry` verification snippet (with comment: "not all plugins declare collections")
  4. Earthdata auth setup (NASA sensors only)
- Remove all developer/Polylith content.
- Add frontmatter redirect from `installation.md` if MkDocs supports it, or update all internal links.

**Result:**
- Wrote `docs/using-plugins.md` with core install, plugin table, registry snippet, and Earthdata auth.
- Deleted `docs/installation.md`; updated internal links in `docs/index.md` and `README.md`.
- Updated `mkdocs.yml` nav entry from `installation.md` to `using-plugins.md`.
- `pytest test/components/aer/grid/ test/components/aer/eoids/` — 53 passed.
- `uv run mkdocs build --strict` — 0 warnings, exit 0.

#### Task 4.3: Create `docs/contributing/dev-setup.md` ✅ DONE
**File:** `docs/contributing/dev-setup.md`
**Action:**
- Move "For Developers" section from old `installation.md`.
- Cover: clone, `uv sync`, Polylith workspace basics, `hatch-polylith-bricks` dev mode, plugin discovery mechanics.
- Add cross-link from `contributing.md`.

**Result:**
- Created `docs/contributing/dev-setup.md` with Prerequisites, Clone and Install, Polylith Workspace overview, Plugin Discovery Mechanics, and hatch-polylith-bricks Dev Mode sections.
- Added cross-link in `docs/contributing.md` pointing to `contributing/dev-setup.md`.
- Updated `mkdocs.yml` nav to nest `contributing.md` and `contributing/dev-setup.md` under a `Contributing` section.
- `pytest test/components/aer/grid/ test/components/aer/eoids/` — 53 passed.
- `uv run mkdocs build --strict` — 0 warnings, exit 0.

#### Task 4.4: Create `docs/pipeline.md` ✅ DONE
**File:** `docs/pipeline.md`
**Action:**
- Write unified user guide with H2 sections: Search, Prepare, Extract.
- Each section: purpose, minimal example, key parameters, common pattern, return-value inspection, gotcha.
- Cross-link to `pipeline-architecture.md` for sequence diagrams and schema tables.
- Cross-link to `grid.md` for grid parameters.

**Result:**
- Wrote `docs/pipeline.md` as a practical user guide with H2 sections for Search, Prepare, and Extract.
- Each section includes: purpose sentence, minimal runnable example, key parameters table, common pattern, return-value inspection, and a gotcha.
- Cross-links to `pipeline-architecture.md` for deep technical reference and to `grid.md` for grid parameters.
- Includes EOIDS mosaicking example in the Extract section.
- `pytest test/components/aer/grid/ test/components/aer/eoids/` — 53 passed.
- `uv run mkdocs build --strict` — 0 warnings, exit 0.
- `uv run basedpyright bases/aer/client/core.py` — 0 errors, 0 warnings, 0 notes.

#### Task 4.5: Expand `docs/grid.md`
**File:** `docs/grid.md`
**Action:**
- Add `GridDefinition` — how to create one from an AOI, cell size, snapping.
- Explain `target_grid_dist` (cell size in meters) vs. profile `resolution` (pixel size in meters).
- Explain `target_grid_overlap` boolean.
- Document grid filtering modes: `intersection`, `within`, `coverage` with `min_coverage`.
- Add small ASCII or Mermaid diagram showing which cells survive each filter.
- Link to `examples/grid/grid_filter_modes_demo.ipynb` for interactive visualization.

#### Task 4.6: Improve `docs/index.md`
**File:** `docs/index.md`
**Action:**
- Rephrase tagline to: "Plugin-based satellite data extraction — from search to analysis-ready Major TOM grid in minutes."
- Add 5-line tl;dr code block before the full example.
- Add simple Mermaid architecture diagram after the "What is AER?" section.
- Keep existing HTML comment placeholders (user request).
- Update documentation table to link to Quick Start, Running the Pipeline, Using Plugins, etc.

#### Task 4.7: Add human-written intro to `docs/api/client.md`
**File:** `docs/api/client.md`
**Action:**
- Add 3–4 sentences before `::: aer.client`:
  > `AerClient` is the single entry point for almost all AER workflows. Create one instance and call `search()`, `prepare_for_extraction()`, and `extract_batches()` in sequence. The sections below document every parameter and return type.
- Add a 5-line example code block.

#### Task 4.8: Fix `docs/build-your-own-plugin.md` YAML error
**File:** `docs/build-your-own-plugin.md`
**Action:**
- Change `collections: ["acme-l1"]` to `collections: {"acme-l1": ["B01"]}` in the YAML snippet.

#### Task 4.9: Fix `docs/contributing.md` clone URL
**File:** `docs/contributing.md`
**Action:**
- Replace `github.com/<org>/aer.git` with `github.com/frandorr/aer.git`.

#### Task 4.10: Remove `docs/last_session.md` from published docs
**File:** `docs/last_session.md`
**Action:**
- Move to repo root as `last_session.md` or `notes.md`, or delete if no longer needed.
- Ensure it is no longer in the `docs/` directory so `--strict` stops flagging it.

#### Task 4.11: Handle orphaned `codemap.csv` and `schema.puml`
**File:** `docs/codemap.csv`, `docs/schema.puml`
**Action:**
- If referenced by `pipeline-architecture.md`, move to `docs/assets/` or `docs/diagrams/` and update links.
- If truly unused, delete or archive in `docs/assets/orphaned/`.

#### Task 4.12: Sync `README.md` with `docs/index.md`
**File:** `README.md`
**Action:**
- Make `README.md` a concise subset of `docs/index.md`:
  - Tagline, 3 benefit bullets, 5-line tl;dr, link to full docs.
- Remove the full 95-line example from `README.md` (it lives in `docs/index.md` and `quickstart.md`).

#### Task 4.13: Add Examples nav link
**File:** `mkdocs.yml`
**Action:**
- Add an "Examples" nav item under Getting Started or Core Concepts that links to `examples/README.md` content. If MkDocs cannot reference files outside `docs/`, either:
  - Copy/symlink `examples/README.md` into `docs/examples.md`, or
  - Add a `docs/examples.md` page that links to the GitHub repo `examples/` directory.

#### Task 4.14: Update `mkdocs.yml` nav
**File:** `mkdocs.yml`
**Action:**
- Apply the nav structure from Section 3.1.
- Verify `mkdocs build --strict` passes with zero warnings.

## 5. Checklist

When restructuring Getting Started:
1. [ ] `quickstart.md` is a step-by-step narrative with runnable code
2. [ ] `using-plugins.md` covers install, plugin combos, and Earthdata auth only
3. [ ] Developer setup lives in `contributing/dev-setup.md`

When creating the pipeline user guide:
1. [ ] `pipeline.md` has H2 sections for Search, Prepare, Extract
2. [ ] Each section has a minimal example, key parameters, and a gotcha
3. [ ] Cross-links exist to `pipeline-architecture.md` and `grid.md`

When expanding Grid docs:
1. [ ] `grid.md` documents `GridDefinition`
2. [ ] `grid.md` explains `target_grid_dist` vs. `resolution`
3. [ ] `grid.md` documents all three filter modes with a visual diagram
4. [ ] `grid.md` links to the interactive notebook

When fixing build and trust issues:
1. [ ] `quickstart.md` has no undefined variables
2. [ ] `build-your-own-plugin.md` YAML is valid
3. [ ] `contributing.md` has the real clone URL
4. [ ] `last_session.md` is removed from `docs/`
5. [ ] Orphaned files are moved or deleted
6. [ ] `README.md` is a subset of `index.md`
7. [ ] `mkdocs build --strict` passes
8. [ ] Griffe warnings are resolved

When improving the homepage:
1. [ ] Tagline mentions Major TOM grid correctly
2. [ ] tl;dr code block exists at the top
3. [ ] Mermaid diagram is present
4. [ ] Documentation table reflects new nav

When updating API reference:
1. [ ] `api/client.md` has a human-written intro with a short example
