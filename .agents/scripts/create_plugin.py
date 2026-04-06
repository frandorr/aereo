#!/usr/bin/env python3
"""Create a new aer plugin template using the pluggy-based architecture.

This script generates boilerplate for a new aer plugin that uses
the @hookimpl decorator to register with the plugin system.
"""

import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Create a new aer plugin template using pluggy hooks"
    )
    parser.add_argument(
        "--name", required=True, help="Name of the plugin (e.g., earthaccess)"
    )
    parser.add_argument(
        "--hook",
        required=True,
        choices=["search", "prepare_tasks", "extract"],
        help="Hook to implement (search, prepare_tasks, or extract)",
    )
    parser.add_argument(
        "--component", help="Polylith component name (default: hook_name)"
    )
    parser.add_argument(
        "--project", help="Polylith project name (default: aer-hook-name)"
    )

    args = parser.parse_args()

    name = args.name
    hook = args.hook
    component_name = args.component or f"{hook}_{name}"
    project_name = args.project or f"aer-{hook}-{name}"
    project_dir = project_name

    print(f"Creating plugin '{name}' implementing '{hook}' hook")
    print(f"  Component: {component_name}")
    print(f"  Project:   {project_name}")

    # 1. Create Polylith component
    subprocess.run(
        ["uv", "run", "poly", "create", "component", "--name", component_name],
        check=True,
    )

    # 2. Add plugin boilerplate to core.py using @hookimpl
    core_path = f"components/aer/{component_name}/core.py"

    if hook == "search":
        core_content = f'''"""Search plugin implementation for {name}.

This module provides a search plugin that implements the AerSpec.search hook
using pluggy's @hookimpl decorator.
"""

from typing import Any

from pandera.typing.geopandas import GeoDataFrame

from aer.plugin import hookimpl
from aer.search import SearchQuery


class {name.capitalize()}SearchPlugin:
    """Search plugin for {name} data source."""

    @hookimpl
    def search(self, query: SearchQuery) -> GeoDataFrame:
        """Search for satellite data matching the query.

        Parameters
        ----------
        query : SearchQuery
            Search parameters including collections, time range, spatial extent.

        Returns
        -------
        GeoDataFrame
            Search results validated against SearchResultSchema.
        """
        # TODO: Implement your search logic here
        # Example:
        # results = your_api.search(
        #     collections=query.collections,
        #     datetime=query.datetime,
        #     intersects=query.intersects,
        # )
        # return GeoDataFrame(results)
        raise NotImplementedError("Search implementation required")
'''
    elif hook == "prepare_tasks":
        core_content = f'''"""Prepare tasks plugin implementation for {name}.

This module provides a prepare_tasks plugin that implements the
AerSpec.prepare_tasks hook using pluggy's @hookimpl decorator.
"""

from typing import Any

from aer.plugin import hookimpl
from aer.extract import ExtractionTask
from aer.search import SearchQuery


class {name.capitalize()}PreparePlugin:
    """Prepare tasks plugin for {name}."""

    @hookimpl
    def prepare_tasks(self, query: SearchQuery) -> list[ExtractionTask]:
        """Prepare extraction tasks from search results.

        Parameters
        ----------
        query : SearchQuery
            The search query with results.

        Returns
        -------
        list[ExtractionTask]
            Extraction tasks ready for processing.
        """
        # TODO: Implement your task preparation logic here
        # Example:
        # return [
        #     ExtractionTask(
        #         source_url=item.s3_url,
        #         output_path=f"/data/{{item.id}}.nc",
        #     )
        #     for item in query.results
        # ]
        raise NotImplementedError("prepare_tasks implementation required")
'''
    else:  # extract
        core_content = f'''"""Extract plugin implementation for {name}.

This module provides an extract plugin that implements the AerSpec.extract hook
using pluggy's @hookimpl decorator.
"""

from typing import Any

from aer.plugin import hookimpl
from aer.extract import ExtractionTask


class {name.capitalize()}ExtractPlugin:
    """Extract plugin for {name} data source."""

    @hookimpl
    def extract(self, task: ExtractionTask) -> ExtractionTask:
        """Extract data for a single extraction task.

        Parameters
        ----------
        task : ExtractionTask
            Task containing source URL, output path, and parameters.

        Returns
        -------
        ExtractionTask
            The task with updated status (SUCCESS or FAILED).
        """
        # TODO: Implement your extraction logic here
        # Example:
        # try:
        #     download(task.source_url, task.output_path)
        #     task.status = "SUCCESS"
        #     task.output_files = [task.output_path]
        # except Exception as e:
        #     task.status = "FAILED"
        #     task.error = str(e)
        # return task
        raise NotImplementedError("Extract implementation required")
'''

    with open(core_path, "w") as f:
        f.write(core_content)

    # 3. Expose the plugin via __init__.py
    init_path = f"components/aer/{component_name}/__init__.py"
    init_content = f'''from aer.{component_name}.core import {name.capitalize()}{hook.split("_")[0].capitalize()}Plugin

__all__ = ["{name.capitalize()}{hook.split("_")[0].capitalize()}Plugin"]
'''
    with open(init_path, "w") as f:
        f.write(init_content)

    # 4. Create Polylith project
    subprocess.run(
        ["uv", "run", "poly", "create", "project", "--name", project_name], check=True
    )

    # 5. Add plugin entry points to pyproject files
    entry_point_line = f'entry-points."aer.plugins".{component_name} = "aer.{component_name}.core:{name.capitalize()}{hook.split("_")[0].capitalize()}Plugin"\n'

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
    print("\\nNext steps:")
    print(f"  1. Edit {core_path} to implement the {hook} hook")
    print("  2. Run 'uv sync' to install dependencies")
    print(f"  3. Test with: uv run pytest test/components/aer/{component_name}/")


def add_entry_point(toml_path, entry_point_line):
    """Add entry point line to pyproject.toml if not present."""
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
        # Append to the end if we couldn't find a proper spot
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
            brick_line = f'{brick_attr} = "aer/{component_name}"\n'
            lines.insert(i + 1, brick_line)
            break

    with open(toml_path, "w") as f:
        f.writelines(lines)


if __name__ == "__main__":
    main()
