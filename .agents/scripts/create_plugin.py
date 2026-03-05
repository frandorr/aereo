#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Create a new aer plugin template")
    parser.add_argument(
        "--name", required=True, help="Name of the plugin (e.g., earthaccess)"
    )
    parser.add_argument(
        "--category",
        required=True,
        help="Category of the plugin (e.g., search, transform)",
    )
    parser.add_argument(
        "--component", help="Polylith component name (default: category_name)"
    )
    parser.add_argument(
        "--project", help="Polylith project name (default: aer-category-name)"
    )

    args = parser.parse_args()

    name = args.name
    category = args.category
    component_name = args.component or f"{category}_{name}"
    project_name = args.project or f"aer-{category}-{name}"
    # Valid Python project directory will have dashes converted to underscores by poly
    # BUT polylith CLI project directories might retain dashes? Wait, Poly CLI creates `projects/<name_with_underscores>` usually.
    # We will let poly create the project, then determine the path.
    project_dir = project_name.replace("-", "_")

    print(f"Creating plugin '{name}' in category '{category}'")
    print(f"  Component: {component_name}")
    print(f"  Project:   {project_name}")

    # 1. Create Polylith component
    subprocess.run(
        ["uv", "run", "poly", "create", "component", "--name", component_name],
        check=True,
    )

    # 2. Add plugin boilerplate to core.py
    core_path = f"components/aer/{component_name}/core.py"
    core_content = f'''from typing import Any
from aer.plugin import plugin

@plugin(name="{name}", category="{category}")
def {name}_plugin(input_data: Any) -> Any:
    """Implementation for {name} plugin."""
    return input_data
'''
    with open(core_path, "w") as f:
        f.write(core_content)

    # 3. Expose the plugin via __init__.py
    init_path = f"components/aer/{component_name}/__init__.py"
    init_content = f'''from aer.{component_name}.core import {name}_plugin

__all__ = ["{name}_plugin"]
'''
    with open(init_path, "w") as f:
        f.write(init_content)

    # 4. Create Polylith project
    subprocess.run(
        ["uv", "run", "poly", "create", "project", "--name", project_name], check=True
    )

    # 5. Add plugin entry points to pyproject files
    entry_point_line = f'entry-points."aer.plugins".{name} = "aer.{component_name}.core:{name}_plugin"\\n'

    print("Adding entry point to root pyproject.toml...")
    add_entry_point("pyproject.toml", entry_point_line)

    project_toml_path = f"projects/{project_dir}/pyproject.toml"
    if os.path.exists(project_toml_path):
        print(f"Adding entry point to project {project_toml_path}...")
        add_entry_point(project_toml_path, entry_point_line)
        ensure_tool_polylith_brick(project_toml_path, component_name)
    else:
        print(f"Warning: Project dir not found at {project_toml_path}", file=sys.stderr)

    print(f"\\nPlugin {name} created successfully!")


def add_entry_point(toml_path, entry_point_line):
    if not os.path.exists(toml_path):
        return

    with open(toml_path, "r") as f:
        lines = f.readlines()

    # Check if already exists
    if any(entry_point_line.strip() in line for line in lines):
        return

    insert_idx = -1
    in_project = False
    project_end_idx = -1

    # Find [project] section and entry-points
    for i, line in enumerate(lines):
        if line.startswith('entry-points."aer.plugins"'):
            insert_idx = i
        if line.startswith("[project]"):
            in_project = True
            continue
        if in_project and line.startswith("[") and not line.startswith("[project"):
            project_end_idx = i
            in_project = False

    if insert_idx != -1:
        lines.insert(insert_idx + 1, entry_point_line)
    elif project_end_idx != -1:
        lines.insert(project_end_idx, entry_point_line)
    else:
        # Append to the end if we couldn't find a proper spot (assume [project] is the last block)
        lines.append(entry_point_line)

    with open(toml_path, "w") as f:
        f.writelines(lines)


def ensure_tool_polylith_brick(toml_path, component_name):
    """Ensure the project's [tool.polylith] links to the newly created component."""
    with open(toml_path, "r") as f:
        lines = f.readlines()

    brick_attr = f'bricks."../../components/aer/{component_name}"'
    if any(brick_attr in line for line in lines):
        return

    # Find [tool.polylith] section
    for i, line in enumerate(lines):
        if line.startswith("[tool.polylith]"):
            brick_line = f'{brick_attr} = "aer/{component_name}"\\n'
            lines.insert(i + 1, brick_line)
            break

    with open(toml_path, "w") as f:
        f.writelines(lines)


if __name__ == "__main__":
    main()
