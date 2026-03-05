---
name: plugin-creator
description: Use this skill to automatically scaffold and generate boilerplate for new aer plugins. It handles creating Polylith components, projects, and registering entry points in pyproject.toml.
license: MIT
metadata:
  author: AI
  version: "1.0.0"
  domain: scaffolding
  triggers: create plugin, scaffolding plugin, new plugin, generate plugin
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
3. **Entry Points** defined in the codebase's `pyproject.toml` so the `PluginRegistry` can discover the plugin.

## When to Use This Skill

- When a user asks to "create a new plugin", "scaffold a plugin", or "generate a new search plugin".
- When a user wants to extend the capabilities of `aer` with a new instrument, transformation, or integration.

## Core Workflow

To scaffold a plugin, DO NOT create files manually. Instead, use the provided deterministic script.

1. **Invoke the Plugin Creation Script**
   Run `.agents/scripts/create_plugin.py` via your CLI tool:
   ```bash
   .agents/scripts/create_plugin.py --name <plugin_name> --category <plugin_category>
   ```

   **Example**:
   ```bash
   .agents/scripts/create_plugin.py --name "sentinel" --category "search"
   ```

   *(Optional Arguments)*:
   - `--component`: To explicitly set the Polylith component name instead of `category_name`.
   - `--project`: To explicitly set the Polylith project name instead of `aer-category-name`.

2. **Verify the Created Files**
   Use standard commands or tools to verify that:
   - `components/aer/<category>_<name>/core.py` and `__init__.py` were created.
   - The pyproject entry point (`entry-points."aer.plugins".<name> ...`) was successfully injected into `pyproject.toml` at the root and in the new project.

3. **Notify the User**
   Explain to the user the files that were modified/created and that the boilerplate is ready.
   Recommend them to `uv sync` to ensure dependencies match and to manually edit the implementation inside the newly created component `.py` files.

## Constraints

### MUST DO
- Always use `.agents/scripts/create_plugin.py` to ensure deterministic execution, Polylith consistency, and atomic creation.
- Request clarification if the `name` or `category` for the new plugin is ambiguous in the user's instructions.
- Ensure the user runs `uv sync` afterward, or ask if they'd like you to run it.

### MUST NOT DO
- DO NOT manually create the component using raw `mkdir` or `cat`.
- DO NOT manually edit `pyproject.toml` entry points for new module creations; rely on the script.
