---
name: plugin-creator
description: |
  Scaffold a new aer plugin starting from the aer-plugin-template. Guides the user
  through choosing search vs extract, reads existing plugins for inspiration,
  runs setup.sh, and verifies the Polylith scaffolding.
license: MIT
metadata:
  author: AI
  version: "2.0.0"
  domain: scaffolding
  triggers: create plugin, scaffolding plugin, new plugin, generate plugin, build aer plugin
  role: scaffolding
  scope: implementation
  output-format: shell
  related-skills: git-commit, codebase-intro
---

# Plugin Creator (Scaffolding Specialist)

You automate the creation of new `aer` plugins.

In the `aer` ecosystem, a plugin is typically composed of:
1. A **Polylith Component** containing the actual logic (`core.py`, `__init__.py`).
2. A **Polylith Project** that packages the component as an independent artifact.
3. **Entry Points** defined in the project's `pyproject.toml` so the `PluginRegistry` can discover the plugin.

## When to Use This Skill

- When a user asks to "create a new plugin", "scaffold a plugin", or "generate a new search plugin".
- When a user wants to extend the capabilities of `aer` with a new instrument, transformation, or integration.

## Core Workflow

### 1. Determine Plugin Type

Ask the user (or infer from context) what type of plugin they need:

| Type | Base Class | Method(s) to implement | Typical use case |
|------|-----------|------------------------|------------------|
| **Search** | `SearchProvider` | `search()` | Discovering datasets/assets (STAC, CMR, API, etc.) |
| **Extract** | `Extractor` | `extract()` | Processing/searching assets into raster artifacts (GeoTIFF, netCDF, etc.) |

- Search plugins return a `GeoDataFrame[AssetSchema]` with `id`, `collection`, `geometry`, `start_time`, `end_time`, `href`.
- Extract plugins receive an `ExtractionTask` and return a `GeoDataFrame[ArtifactSchema]` with raster output paths and grid metadata.

### 2. Gather Reference Plugins as Context

Before writing any code, **read existing plugins** to learn patterns, conventions, and imports. If you have local clones of the reference repos, read them directly; otherwise fetch the relevant files from GitHub.

**Reference Search Plugins:**
- `aer-search-earthaccess` — NASA Earthdata CMR search via `earthaccess`
  - Repo: `https://github.com/frandorr/aer-search-earthaccess`
  - Component: `components/aer/search_earthaccess/core.py`
- `aer-search-planetary-computer` — Microsoft Planetary Computer STAC search
  - Repo: `https://github.com/frandorr/aer-search-planetary-computer`
  - Component: `components/aer/search_planetary_computer/core.py`
- `aer-search-aws-goes` — AWS GOES ABI search
  - Repo: `https://github.com/frandorr/aer-search-aws-goes`
  - Component: `components/aer/search_aws_goes/core.py`

**Reference Extract Plugins:**
- `aer-extract-odc-stac` — STAC-to-raster via `odc.stac.load`
  - Repo: `https://github.com/frandorr/aer-extract-odc-stac`
  - Component: `components/aer/extract_odc_stac/core.py`
- `aer-extract-aws-goes` — GOES ABI extraction with LUT and ODC engines
  - Repo: `https://github.com/frandorr/aer-extract-aws-goes`
  - Component: `components/aer/extract_aws_goes/core.py`
- `aer-extract-satpy` — Satpy-based extraction
  - Repo: `https://github.com/frandorr/aer-extract-satpy`
  - Component: `components/aer/extract_satpy/core.py`

Also read the base classes to understand the exact signatures:
- `aer/components/aer/interfaces/core.py` — `SearchProvider`, `Extractor`, `AerProfile`, `ExtractionTask`, `GridConfig`
- `aer/components/aer/schemas/core.py` — `AssetSchema`, `ArtifactSchema`

### 3. Bootstrap from the Template

**Do NOT create files manually.** Instead, create a new repository from the template:

```bash
git clone https://github.com/frandorr/aer-plugin-template.git aer-<type>-<name>
cd aer-<type>-<name>
rm -rf .git
```

Then run the setup wizard:

```bash
chmod +x setup.sh
./setup.sh
```

The script will:
1. Validate the project name starts with `aer-`.
2. Install `uv` (if missing) and sync dependencies.
3. Create the Polylith **component** and **project**.
4. Generate `core.py` with the correct base class (`SearchProvider` or `Extractor`).
5. Register the `[project.entry-points."aer.plugins"]` entry point.

### 4. Implement the Plugin Logic

Open the generated `components/aer/<component_name>/core.py` and implement the required methods using the reference plugins as inspiration.

**Key conventions:**
- Always set `supported_collections: Sequence[str] = ["*"]` (or a specific list).
- For search: return an empty-but-valid GeoDataFrame via `self._empty_result()` when there are no matches.
- For extract: read tiling params from `extraction_task.grid_config` and `extraction_task.profile`. Do not hard-code defaults.
- Use `structlog.get_logger()` for logging.
- Use `pandera` schemas (`AssetSchema.validate()`, `ArtifactSchema.validate()`) for DataFrame validation.

### 5. Verify the Scaffolding

Run these commands to ensure everything is wired correctly:

```bash
uv run poly info                    # Check bricks and projects
uv run pytest                       # Run tests (should pass with the placeholder)
python -c "from aer.<component_name>.core import <ClassName>; print('OK')"
```

### 6. Add Dependencies

If the plugin needs extra libraries (e.g., `requests`, `pystac-client`, `geoai-py`), add them:

```bash
uv add <package-name>
```

## Constraints

### MUST DO
- Always start from `aer-plugin-template` and run `setup.sh`.
- Always read at least one reference plugin before implementing.
- Always read `aer/components/aer/interfaces/core.py` to confirm current base-class signatures.
- Request clarification if the plugin type (search vs extract) or name is ambiguous.
- Ensure the user runs `uv sync` after scaffolding.

### MUST NOT DO
- Do NOT manually create components with raw `mkdir` or `cat`.
- Do NOT manually edit `pyproject.toml` entry points; let `setup.sh` handle it.
- Do NOT use the old `@hookimpl` / pluggy patterns (deprecated).
