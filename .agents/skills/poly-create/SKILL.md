---
name: poly-create
description: Create a Polylith component, base, or project using uv poly.
license: MIT
metadata:
  author: AI
  version: "1.0.0"
  triggers: create component, create base, create project, new component, new base, new project
  role: scaffolding
  scope: implementation
---

# Polylith Creator (Scaffolding Specialist)

You automate the creation of new Polylith pieces (components, bases, or projects) using the `uv poly` command.

## When to Use This Skill

- When a user asks to "create a new component", "create a base", or "create a project".
- When a user wants to scaffold a new piece of the Polylith architecture.

## Core Workflow

To create a Polylith piece, follow these steps:

1. **Identify the Type**
   Determine if the user wants to create a `component`, `base`, or `project`. If the type is not specified, ask for clarification.

2. **Identify the Name**
   Determine the name for the item. If not specified, ask for it.

3. **Identify the Description**
   Check if the user provided a description. If not, ask if they want to add one. Interpret and complete any simple descriptions provided, as they will be used for the `__init__.py` docstring.

4. **Construct and Execute the Command**
   Formulate and run the command in the workspace root:
   ```bash
   uv run poly create <type> --name "<name>" --description "<description>"
   ```
   If no description is provided:
   ```bash
   uv run poly create <type> --name "<name>"
   ```

5. **Verify and Notify**
   Confirm that the item was created in the correct directory (e.g., `components/aer/<name>`) and inform the user.

## Constraints

### MUST DO
- Always use `uv run poly create` for consistency with the Polylith architecture.
- Ensure the name follows the project's naming conventions.
- Provide a clear docstring if a description is available.

### MUST NOT DO
- DO NOT manually create directories or `__init__.py` files if `uv run poly create` can do it.
- DO NOT skip the verification step.
