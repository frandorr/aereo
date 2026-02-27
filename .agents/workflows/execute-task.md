---
name: execute-task
description: Execute a coding task using docs/codemap.csv as an index to load relevant context, then implement the solution following polylith conventions.
---

# Execute Task

Given a task prompt, use the codebase index at `docs/codemap.csv` to load relevant context and implement the solution.

## Workflow

### Step 1: Ensure codemap is up to date

Before starting, regenerate the index to make sure it reflects the latest codebase state:

```bash
.agent/scripts/codemap/target/release/codemap . docs/codemap.csv
```

If the binary doesn't exist yet, build it first (see `.agent/skills/codebase-mapper.md`).

### Step 2: Read the codemap index

Read `docs/codemap.csv`. This pipe-delimited file has columns:

```
filepath|summary|public_api|dependencies
```

Each **component row** (e.g. `components/<project>/<name>`) shows:
- What the component does (`summary`)
- What it exposes (`public_api`)
- What it depends on (`dependencies`)

Each **module row** (e.g. `components/<project>/<name>/core.py`) shows
the individual file's summary and dependencies.

### Step 3: Identify relevant components

From the task prompt, identify keywords and match them against the codemap:

1. **Search `summary` and `public_api`** for direct keyword matches
2. **Search `filepath`** for component names that relate to the task
3. **Follow the dependency chain**: for each relevant component, check its `dependencies` column
   and include those components too (they are likely needed as context)
4. **Check reverse dependencies**: search the `dependencies` column for components that depend on
   the relevant components — these are peers that follow the same patterns

#### Heuristic: Which files to load

- **Always load** the `__init__.py` of identified components (to see the public API)
- **Always load** the `core.py` of the most relevant components (to understand implementation patterns)
- **Load base classes** by following the dependency chain upward (e.g., if implementing an extractor,
  load `extractor/core.py` to see the abstract base class)
- **Load sibling implementations** for similar components to follow established patterns
  (e.g., if implementing a new satellite extractor, load an existing one like `viirs_satpy_extractor/core.py`)
- **Load test files** for sibling components to understand the expected testing patterns
- **Skip development/ and test/ files** unless the task specifically involves them

#### Example: Task = "Implement TOA extraction for VIIRS SDR"

1. Search codemap for "extract", "VIIRS", "TOA" → find:
   - `components/<project>/extractor` (base class)
   - `components/<project>/viirs_satpy_extractor` (existing VIIRS extractor)
   - `components/<project>/definitions` (has VIIRSBand, SensorRevisit, etc.)
2. Check dependencies of `viirs_satpy_extractor`: `definitions, extractor, grid, repository, settings`
3. Load sibling extractors like `goes_satpy_extractor` and `modis_satpy_extractor` to see patterns
4. Load relevant test files to understand testing patterns

### Step 4: Load files as context

Read the identified files. Prioritize reading in this order:

1. **Abstractions first**: Base classes and interfaces (`extractor/core.py`, `repository/core.py`, etc.)
2. **Definitions**: Data models and types (`definitions/core.py`)
3. **Sibling implementations**: Existing similar components to follow patterns
4. **Configuration**: Settings, configs that might be needed
5. **Tests**: Test patterns for similar components

### Step 5: Understand the patterns

Before writing code, identify the codebase conventions from what you loaded:

- **File structure**: Each component has `__init__.py` (public API) + `core.py` (implementation)
- **Import style**: `from <project>.<component> import <symbol>` (use the public API, not internal modules)
- **Class patterns**: Abstract base classes in base components, concrete implementations in specific components
- **Naming conventions**: Follow existing naming (e.g., `*Extractor`, `*Fetcher`, `*LUT`)
- **Error handling**: Follow the pattern used in sibling components
- **Logging**: Check if the project uses `structlog`, `logging`, or similar
- **Type hints**: Match the type annotation style used in the codebase
- **`__all__` exports**: Every component must define `__all__` in `__init__.py`

### Step 6: Implement the task

Follow the polylith structure when creating or modifying code:

#### Creating a new component

1. Create the component directory: `uv run poly create component --name <component_name> --description <component_description>`

#### Modifying an existing component

1. Edit the relevant `.py` files
2. If adding new public symbols, update `__init__.py` and `__all__`
3. Update or add tests

#### Adding development scripts

1. Create in `development/` directory
2. Import from components using the public API: `from <project>.<component> import ...`

### Step 7: Verify

After implementing:

1. **Check imports**: Ensure all imports use the public API (`from <project>.<component> import ...`)
2. **Check `__all__`**: Any new public symbols must be in the component's `__all__`
3. **Run linting** if configured (check `pyproject.toml` for ruff/pyright settings):
   ```bash
   ruff check components/<project>/<component_name>/
   ```
4. **Run tests** for the affected component:
   ```bash
   python -m pytest test/components/<project>/<component_name>/ -v
   ```
5. **Run related tests**: If your change touches base classes or shared components,
   run tests for downstream dependents too (find them via `dependencies` column in codemap)

### Step 8: Update the codemap

After making changes, regenerate the index:

```bash
.agent/scripts/codemap/target/release/codemap . docs/codemap.csv
```

This ensures the codemap stays in sync with the codebase for future tasks.

## Quick Reference: Polylith Conventions

| Convention | Rule |
|---|---|
| Component location | `components/<project>/<name>/` |
| Base location | `bases/<project>/<name>/` |
| Public API | Defined in `__init__.py` via `__all__` |
| Main implementation | `core.py` (most components follow this) |
| Import style | `from <project>.<component> import Symbol` |
| Test location | `test/components/<project>/<name>/test_core.py` |
| Integration tests | `test/integration/test_<description>.py` |
| Dev scripts | `development/<script>.py` |
| Settings | Read from environment via settings component |

## Context Budget Guidelines

To avoid overloading context, follow these limits:

- **Small task** (modify existing code): Load 3-5 files (~500-1000 lines)
- **Medium task** (new feature in existing component): Load 5-10 files (~1000-2000 lines)
- **Large task** (new component): Load 8-15 files (~2000-4000 lines)

Always prioritize **abstractions and sibling patterns** over loading everything.
If a component has many files, read `__init__.py` first to understand the API,
then only load the specific files relevant to your task.
