---
name: plugin-creator
description: |
  Scaffold a new aereo plugin starting from the aereo-plugin-template. Guides the user
  through choosing search vs extract, reads existing plugins for inspiration,
  runs setup.sh, and verifies the Polylith scaffolding.
license: MIT
metadata:
  author: AI
  version: "2.2.0"
  domain: scaffolding
  triggers: create plugin, scaffolding plugin, new plugin, generate plugin, build aereo plugin
  role: scaffolding
  scope: implementation
  output-format: shell
  related-skills: git-commit, codebase-intro
---

# Plugin Creator (Scaffolding Specialist)

You automate the creation of new `aereo` plugins.

In the `aereo` ecosystem, a plugin is typically composed of:
1. A **Polylith Component** containing the actual logic (`core.py`, `__init__.py`).
2. A **Polylith Project** that packages the component as an independent artifact.
3. **Entry Points** defined in the project's `pyproject.toml` so the `PluginRegistry` can discover the plugin.

## When to Use This Skill

- When a user asks to "create a new plugin", "scaffold a plugin", or "generate a new search plugin".
- When a user wants to extend the capabilities of `aereo` with a Search or Extraction plugin.

## Core Workflow

### 1. Determine Plugin Type

Ask the user (or infer from context) what type of plugin they need, interfaces located at aereo/components/aereo/interfaces/core.py, schemas in aereo/components/aereo/schemas/core.py:

| Type | Base Class | Method(s) to implement | Typical use case |
|------|-----------|------------------------|------------------|
| **Search** | `SearchProvider` | `search()` | Discovering datasets/assets (STAC, CMR, API, etc.) |
| **Extract** | `Extractor` | `extract()` | Processing/searching assets into raster artifacts (GeoTIFF, netCDF, etc.) |

- Search plugins implements "search" method and return a `GeoDataFrame[AssetSchema]`
- Extract plugins implement the pipeline stages in an `ExtractConfig` (reader, reprojector, processor, writer) and produce a `GeoDataFrame[ArtifactSchema]` with raster output paths and grid metadata. Task preparation is handled by a `TaskBuilder` plugin.

### 2. Gather Reference Plugins as Context

Before writing any code, **read existing plugins** to learn patterns, conventions, and imports. If you have local clones of the reference repos, read them directly; otherwise fetch the relevant files from GitHub.

**Reference Search Plugins:**
- `aereo-search-earthaccess` — NASA Earthdata CMR search via `earthaccess`
  - Repo: `https://github.com/frandorr/aereo-search-earthaccess`
  - Component: `components/aereo/search_earthaccess/core.py`
- `aereo-search-planetary-computer` — Microsoft Planetary Computer STAC search
  - Repo: `https://github.com/frandorr/aereo-search-planetary-computer`
  - Component: `components/aereo/search_planetary_computer/core.py`
- `aereo-search-aws-goes` — AWS GOES ABI search
  - Repo: `https://github.com/frandorr/aereo-search-aws-goes`
  - Component: `components/aereo/search_aws_goes/core.py`

**Reference Extract Plugins:**
- `aereo-extract-odc-stac` — STAC-to-raster via `odc.stac.load`
  - Repo: `https://github.com/frandorr/aereo-extract-odc-stac`
  - Component: `components/aereo/extract_odc_stac/core.py`
- `aereo-extract-aws-goes` — GOES ABI extraction with LUT and ODC engines
  - Repo: `https://github.com/frandorr/aereo-extract-aws-goes`
  - Component: `components/aereo/extract_aws_goes/core.py`
- `aereo-extract-satpy` — Satpy-based extraction
  - Repo: `https://github.com/frandorr/aereo-extract-satpy`
  - Component: `components/aereo/extract_satpy/core.py`

Also read the base classes to understand the exact signatures:
- `aereo/components/aereo/interfaces/core.py` — `SearchProvider`, `Extractor`, `AereoProfile`, `ExtractionTask`, `GridConfig`
- `aereo/components/aereo/schemas/core.py` — `AssetSchema`, `ArtifactSchema`

### 3. Bootstrap from the Template

**Do NOT create files manually.** Instead, create a new repository from the template:

```bash
git clone https://github.com/frandorr/aereo-plugin-template.git aereo-<type>-<name>
cd aereo-<type>-<name>
rm -rf .git
```

Then run the setup wizard:

```bash
chmod +x setup.sh
./setup.sh
```

The script will:
1. Validate the project name starts with `aereo-`.
2. Install `uv` (if missing) and sync dependencies.
3. Create the Polylith **component** and **project**.
4. Generate `core.py` with the correct base class (`SearchProvider` or `Extractor`).
5. Register the `[project.entry-points."aereo.plugins"]` entry point.

#### Important: Fix namespace and naming bugs in the template

The template may still contain outdated `aer` references. After `setup.sh` finishes, verify and fix these:

1. **Workspace namespace**: Check `workspace.toml` — if it says `namespace = "aer"`, change it to `namespace = "aereo"`.
2. **Root pyproject.toml keywords**: If the keywords list contains `"aer"`, change it to `"aereo"`.
3. **Project directory name**: The `setup.sh` may create `projects/aer-<name>/` instead of `projects/aereo-<name>/`. Rename it if needed:
   ```bash
   mv projects/aer-<name> projects/aereo-<name>
   ```
4. **Project pyproject.toml name**: Update `projects/aereo-<name>/pyproject.toml` to have `name = "aereo-<name>"` (not `aer-<name>`).
5. **Wheel packages**: In the project `pyproject.toml`, ensure `build.targets.wheel.packages = ["aereo"]` (not `["aer"]`).
6. **Polylith bricks**: In the project `pyproject.toml`, ensure bricks map to `aereo/<component>` not `aer/<component>`.

### 4. Implement the Plugin Logic

Open the generated `components/aereo/<component_name>/core.py` and implement the required methods using the reference plugins as inspiration.

**Key conventions:**
- For every plugins, always set `supported_collections: Sequence[str] = ["*"]` (or a specific list) and recommend adding params metadata with `required_params` and `optional_params`. Those will be used by the plugin manager to validate and document the plugin's parameters and give helpful hints to the user.
- For search: return an empty-but-valid GeoDataFrame via `self._empty_result()` when there are no matches.
- For extract: read tiling params from `extraction_task.grid_config` and `extraction_task.profile`. Do not hard-code defaults.
- Use `structlog.get_logger()` for logging.
- Use `pandera` schemas (`AssetSchema.validate()`, `ArtifactSchema.validate()`) for DataFrame validation.

### 5. Ensure Entry Points Are Registered

The project package (not just the workspace root) must be installed as an editable package for the `aereo.plugins` entry points to be discoverable by the `PluginRegistry`.

1. Create a `README.md` inside the project directory if it doesn't exist (hatchling requires it):
   ```bash
   touch projects/aereo-<name>/README.md
   ```

2. Install the project package:
   ```bash
   uv pip install -e projects/aereo-<name> --no-deps
   ```

3. Verify the entry point is registered:
   ```bash
   uv run python -c "
   import importlib.metadata
   for ep in importlib.metadata.entry_points().select(group='aereo.plugins'):
       print(f'{ep.name} = {ep.value}')
   "
   ```

You should see your plugin listed (e.g., `extract_lazycogs = aereo.extract_lazycogs.core:ExtractLazycogs`). If it's missing, the `PluginRegistry` will raise `ValueError: Hinted plugin '...' is not a registered Extractor/SearchProvider`.

### 6. Verify the Scaffolding

Run these commands to ensure everything is wired correctly:

```bash
uv run poly info                    # Check bricks and projects
uv run pytest                       # Run tests (should pass with the placeholder)
python -c "from aereo.<component_name>.core import <ClassName>; print('OK')"
```

### 7. Add Dependencies

If the plugin needs extra libraries (e.g., `requests`, `pystac-client`, `geoai-py`), add them:

```bash
uv add <package-name>
```

**Important:** The plugin's *project* `pyproject.toml` (`projects/aereo-<name>/pyproject.toml`) must declare its runtime dependencies, not just `"aereo"`. When the aereo workspace installs your plugin as an editable package, `uv` resolves dependencies from the project's `pyproject.toml`. If you import `rustac` in `core.py` but don't list it in the project dependencies, you'll get `ModuleNotFoundError` at runtime.

For example, a search plugin that uses `rustac` should have:
```toml
[project]
dependencies = [
    "aereo",
    "rustac>=0.9.11,<0.10.0",
]
```

### 8. Register the Plugin in the Aereo Workspace

This is the **most common cause** of `ValueError: Hinted plugin '...' is not a registered ...`. The plugin project must be declared as a workspace dependency so `uv` installs it and exposes its entry points.

In the **aereo workspace** `pyproject.toml` (the main repo, not the plugin repo), add two things:

1. **Add to `[tool.uv.sources]`** (pointing at the plugin's *project* directory, not the workspace root):
   ```toml
   [tool.uv.sources]
   aereo-<name> = { path = "../aereo-<name>/projects/aereo-<name>", editable = true }
   ```
   - The path must end in `projects/aereo-<name>` — that's the directory with the entry points.
   - If the plugin is a sibling of the aereo repo, the path is `../aereo-<name>/projects/aereo-<name>`.

2. **Add to `[dependency-groups] dev`** so it gets installed when you `uv sync`:
   ```toml
   [dependency-groups]
   dev = [
     "...",
     "aereo-<name>",
   ]
   ```

3. **Match `requires-python`** between the plugin and the aereo workspace. If aereo says `requires-python = ">=3.12"`, the plugin project `pyproject.toml` must not say `">=3.13"` or `uv` will fail to resolve.

4. **Run `uv sync` in the aereo workspace**:
   ```bash
   cd /path/to/aereo
   uv sync
   ```

5. **Verify** — from inside the aereo workspace, check all registered entry points:
   ```bash
   uv run python -c "
   import importlib.metadata
   for ep in importlib.metadata.entry_points().select(group='aereo.plugins'):
       print(f'{ep.name} = {ep.value}')
   "
   ```
   You should see your plugin listed.

## Constraints

### MUST DO
- Always start from `aereo-plugin-template` and run `setup.sh`.
- Always read at least one reference plugin before implementing.
- Always read `aereo/components/aereo/interfaces/core.py` and `aereo/components/aereo/schemas/core.py` to confirm current base-class and schema signatures.
- Always fix `aer` → `aereo` namespace issues after running `setup.sh`.
- Always install the project package with `uv pip install -e projects/aereo-<name> --no-deps` and verify entry points are registered.
- Always register the plugin in the **aereo workspace** `pyproject.toml` (`[tool.uv.sources]` + `[dependency-groups] dev`) and run `uv sync` there.
- Request clarification if the plugin type (search vs extract) or name is ambiguous.
- Ensure the user runs `uv sync` after scaffolding.

### MUST NOT DO
- Do NOT manually create components with raw `mkdir` or `cat`.
- Do NOT manually edit `pyproject.toml` entry points; let `setup.sh` handle it (then fix the `aer`/`aereo` naming bugs).
