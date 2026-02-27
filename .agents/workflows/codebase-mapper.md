---
name: codebase-mapper
description: Map a Python Polylith codebase structure, extracting public APIs, summaries, and dependency graphs into docs/codemap.csv for agent context loading.
---

# Codebase Mapper

Generates a structured index of a **Python Polylith** codebase at `docs/codemap.csv`.
This file is used by agents as a lightweight index to understand what code exists and
selectively load only the files they need as context.

## How It Works

The parser reads `pyproject.toml` to auto-detect:
- **Project name** from `[project].name` (e.g. `aer`, `mylib`)
- **Source directories** from `[tool.hatch.build].dev-mode-dirs` (defaults to `["components", "bases", "development"]`)

It then uses the project name to:
- Find namespace packages (e.g. `components/<project_name>/`)
- Detect internal dependencies via `from <project_name>.* import ...` patterns

This makes the tool **reusable across any Python Polylith repository** — just point it at the project root.

## Output Format

The output is a **pipe-delimited CSV** at `docs/codemap.csv` with columns:

| Column | Description |
|---|---|
| `filepath` | Relative path to the component directory or Python file |
| `summary` | One-line description extracted from the module docstring |
| `public_api` | Comma-separated list of names from `__all__` in `__init__.py` |
| `dependencies` | Comma-separated list of internal component names this module imports |

### Row types

- **Component rows** (`components/<project>/<name>`) — aggregated view of a polylith component.
  Public API comes from `__init__.py`; dependencies are merged from all `.py` files in the component.
- **Module rows** (`components/<project>/<name>/<file>.py`) — individual source files with their own
  summary and dependency list (public_api is empty since it's exposed via `__init__.py`).
- **Development rows** (`development/*.py`) — standalone scripts/bases.
- **Test rows** (`test/**/*.py`) — test files with their dependencies.

## How to Run

### Prerequisites

The parser is a compiled Rust binary. If it hasn't been built yet, build it first:

```bash
cd .agent/scripts/codemap && cargo build --release
```

### Generate the codemap

```bash
.agent/scripts/codemap/target/release/codemap . docs/codemap.csv
```

This runs in **~20ms** and produces the full index.

### One-liner (build + run)

```bash
cd .agent/scripts/codemap && cargo build --release 2>&1 && cd - && .agent/scripts/codemap/target/release/codemap . docs/codemap.csv
```

## How Agents Should Use codemap.csv

### 1. Load the index first

Before exploring the codebase, read `docs/codemap.csv` to understand:
- What components exist and what they expose
- The dependency graph between components
- Which files contain relevant functionality

### 2. Identify relevant components

Search the `summary` and `public_api` columns for keywords related to your task.
For example, if working on satellite data extraction:

```
grep "extract" docs/codemap.csv
```

### 3. Load only what you need

Use the `filepath` column to load specific files. Follow the dependency chain:
- Start with the component you need
- Check its `dependencies` column to find related components
- Load those as needed

### 4. Understand the polylith structure

The codebase follows the **Python Polylith** architecture:

- **`components/<project>/<name>/`** — Reusable library components. Each has:
  - `__init__.py` — Public API surface (re-exports from internal modules)
  - `core.py` — Main implementation
  - Other `.py` files — Supporting modules
- **`bases/<project>/<name>/`** — Base components (entry points, same structure as components)
- **`development/`** — Development scripts and bases (not shipped in packages)
- **`test/`** — Unit and integration tests mirroring the component structure
- **`projects/`** — Deployable project configurations (workspace members)

Import convention: `from <project>.<component_name> import <symbol>`

### Example: Finding how data extraction works

1. Read `docs/codemap.csv`
2. Find the extractor component → see its public API and dependencies
3. Find concrete implementations (components with `extractor` in their dependencies)
4. Load only the files you need for your task

## Auto-detection Details

The parser reads `pyproject.toml` at the project root:

```toml
[project]
name = "myproject"          # ← used as the namespace / import prefix

[tool.hatch.build]
dev-mode-dirs = ["components", "bases", "development", "."]
```

From this it derives:
- **Namespace dir**: For each dev-mode-dir, checks if `<dir>/<project_name>/` exists
  - If yes → treats it as a polylith brick root (scans subdirectories as components)
  - If no → treats it as a standalone source directory (scans `.py` files recursively)
- **Import prefix**: `from <project_name>.` — used to detect internal dependencies
- **Test dir**: Always scans `test/` if it exists

If `dev-mode-dirs` is not specified, defaults to `["components", "bases", "development"]`.

## Parser Source

The Rust source lives at `.agent/scripts/codemap/src/main.rs`.

### Rebuilding

```bash
cd .agent/scripts/codemap && cargo build --release
```

## When to Regenerate

Regenerate `docs/codemap.csv` when:
- New components are added
- Public APIs change (modifications to `__init__.py`)
- Files are renamed or moved
- After significant refactoring

The generation is fast enough (~20ms) to run on every relevant change.
