---
name: execute-task
description: Execute a coding task using docs/codemap.csv as an index to load relevant context, then implement the solution following polylith conventions.
license: MIT
metadata:
  author: AI
  version: "1.0.0"
  triggers: execute task, implement feature, fix bug, coding task
  role: implementation
  scope: implementation
---

# Task Executor (Implementation Specialist)

You implement coding tasks by leveraging the codebase index (`docs/codemap.csv`) to load precise context and following Polylith architectural conventions.

## Core Workflow

1. **Update Index**
   Regenerate the codemap: `.agent/scripts/codemap/target/release/codemap . docs/codemap.csv`.

2. **Identify Context**
   Search `docs/codemap.csv` for keywords. Match against `summary`, `public_api`, and `filepath`. Follow dependencies to find related components.

3. **Load Relevant Files**
   - **Abstractions first**: Base classes and interfaces.
   - **Definitions**: Data models and types.
   - **Sibling implementations**: Follow existing patterns.
   - **Tests**: Understand testing requirements.

4. **Understand Patterns**
   Identify naming conventions, import styles (`from <project>.<component> import ...`), error handling, and type hint usage.

5. **Implement**
   - Create new components via `uv run poly create component`.
   - Update `__init__.py` and `__all__` when modifying public APIs.
   - Follow the existing Polylith structure.

6. **Verify**
   - Check imports use the public API.
   - Run linting: `ruff check components/<project>/<component>/`.
   - Run tests: `python -m pytest test/components/<project>/<component>/ -v`.

7. **Finalize**
   Regenerate the codemap to reflect your changes.

## Polylith Conventions Quick Reference

| Item | Convention |
|---|---|
| Component | `components/<project>/<name>/` |
| Public API | `__init__.py` + `__all__` |
| Imports | `from <project>.<component> import Symbol` |
| Tests | `test/components/<project>/<name>/` |

## Constraints

### MUST DO
- Load only the minimum necessary files to preserve context budget.
- Use the public API of components for all internal imports.
- Add/update tests for every change.

### MUST NOT DO
- DO NOT bypass the Polylith architecture by importing from internal modules.
- DO NOT forget to update `__all__` in `__init__.py` for new public symbols.
