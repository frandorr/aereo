---
description: Create a Polylith component, base, or project using uv poly
---

Follow these steps to create a new Polylith piece (component, base, or project):

1. **Identify the type**: Determine if the user wants to create a `component`, `base`, or `project`. If the user has not specified the type, ask them to provide one.
2. **Identify the name**: Determine the `--name` for the item. If the user has not specified a name, ask them to provide it.
3. **Identify the description based on what user explains**: Check if the user has provided a description. If not, you may ask if they want to add one. The user might give a simple description that you should interprete and complete. This will be used as __init__.py docstring so it's important.
4. **Construct the command**: Formulate the command based on the inputs: `uv run poly create <type> --name "<name>" --description "<description>"`. If no description was provided, simply use `uv run poly create <type> --name "<name>"`.
// turbo
5. **Execute the command**: Run the constructed command in the workspace root directory using the `run_command` tool.
