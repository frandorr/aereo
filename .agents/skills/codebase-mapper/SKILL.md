---
name: codebase-mapper
description: Map a Python Polylith codebase structure, extracting public APIs, summaries, and dependency graphs into docs/codemap.csv for agent context loading.
license: MIT
metadata:
  author: AI
  version: "1.0.0"
  triggers: map codebase, generate codemap, index codebase, scan codebase
  role: indexing
  scope: research
---

# Codebase Mapper (Indexing Specialist)

You generate a structured index of a **Python Polylith** codebase at `docs/codemap.csv`. This file is used as a lightweight index to understand what code exists and selectively load only the necessary files as context.

## When to Use This Skill

- When new components are added or public APIs change.
- When files are renamed or moved.
- After significant refactoring.
- Before starting a new task to ensure you have the latest codebase state.

## Core Workflow

1. **Build the Parser (if needed)**
   The parser is a Rust binary. If not built:
   ```bash
   cd .agent/scripts/codemap && cargo build --release
   ```

2. **Generate the Codemap**
   Run the parser from the workspace root:
   ```bash
   .agent/scripts/codemap/target/release/codemap . docs/codemap.csv
   ```
   *(One-liner: `cd .agent/scripts/codemap && cargo build --release 2>&1 && cd - && .agent/scripts/codemap/target/release/codemap . docs/codemap.csv`)*

3. **Analyze the Output**
   The `docs/codemap.csv` is pipe-delimited with columns: `filepath`, `summary`, `public_api`, `dependencies`. Use it to:
   - Identify relevant components via `summary` and `public_api`.
   - Follow the dependency graph between components.
   - Understand the Polylith structure (`components/`, `bases/`, `projects/`).

## Polylith Structure Reference

- **`components/<project>/<name>/`**: Reusable logic. `__init__.py` defines the public API.
- **`bases/<project>/<name>/`**: Entry points (APIs, CLIs).
- **`projects/`**: Deployable configurations.
- **`test/`**: Unit and integration tests.
- **Import convention**: `from <project>.<component_name> import <symbol>`

## Constraints

### MUST DO
- Always regenerate the codemap after making structural changes.
- Use the codemap to minimize context usage by loading only relevant files.
- Respect the Polylith import convention.

### MUST NOT DO
- DO NOT rely on an outdated `codemap.csv`.
- DO NOT load unnecessary files if the codemap can help you filter them.
