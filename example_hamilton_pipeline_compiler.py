"""Example: dynamic Hamilton pipeline compilation from AEREO config.

This answers the question: "If all plugins are discovered, how do I control
which ones run and in what order?"

Answer: compile the config into a Hamilton DAG at runtime.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

import xarray as xr

# ---------------------------------------------------------------------------
# 1.  Discovered plugin functions (from 3rd-party modules)
# ---------------------------------------------------------------------------
# These are auto-discovered via entry points. They exist in the DAG but
# only run if something depends on them.


def filter_clouds(ds: xr.Dataset, max_cloud: float = 20.0) -> xr.Dataset:
    """Drop scenes with > max_cloud % cloud cover."""
    ...


def filter_nan(ds: xr.Dataset, vars_to_check: Sequence[str]) -> xr.Dataset:
    """Drop pixels that are NaN in all listed variables."""
    ...


def ndvi(ds: xr.Dataset, red_band: str, nir_band: str) -> xr.Dataset:
    """Compute NDVI and append as a new variable."""
    ...


# ---------------------------------------------------------------------------
# 2.  Pipeline compiler — turns a config list into a Hamilton DAG
# ---------------------------------------------------------------------------
# This is the missing piece.  Hamilton discovers nodes, but the pipeline
# *author* decides which nodes to wire together.  We do that by generating
# wrapper functions whose signatures create the dependency chain.


def compile_pipeline(
    steps: Sequence[str | dict[str, Any]],
    plugin_functions: Mapping[str, Callable],
) -> dict[str, Callable]:
    """Turn an ordered config list into a dict of Hamilton-ready functions.

    Args:
        steps: Ordered list of step names, e.g.
               ``["filter_clouds", {"filter_nan": {"vars_to_check": ["B04"]}}]``
        plugin_functions: Mapping of function name -> callable (from discovery).

    Returns:
        A dict of dynamically-created functions ready to be added to a
        Hamilton driver via ``.with_functions()`` or by injecting into a
        temporary module.
    """
    compiled: dict[str, Callable] = {}

    prev_output = "raw_dataset"  # the starting node name

    for idx, step in enumerate(steps):
        if isinstance(step, dict):
            name, params = next(iter(step.items()))
        else:
            name, params = step, {}

        func = plugin_functions[name]
        output_name = f"step_{idx}_{name}"

        # Create a closure that captures func + params
        def make_node(f, p, out, inp):
            def node(dataset: xr.Dataset) -> xr.Dataset:
                return f(dataset, **p)
            node.__name__ = out
            node.__annotations__ = {"dataset": xr.Dataset, "return": xr.Dataset}
            return node

        compiled[output_name] = make_node(func, params, output_name, prev_output)
        prev_output = output_name

    return compiled


# ---------------------------------------------------------------------------
# 3.  Usage — the pipeline config controls what runs
# ---------------------------------------------------------------------------


def run_from_config():
    from hamilton import driver

    # Discovered from entry points
    all_plugins = {
        "filter_clouds": filter_clouds,
        "filter_nan": filter_nan,
        "ndvi": ndvi,
    }

    # User (or framework author) provides this config
    pipeline_config = [
        "filter_nan",  # only this one — filter_clouds is installed but skipped
    ]

    # Compile to a DAG
    compiled = compile_pipeline(pipeline_config, all_plugins)

    # Build driver with base modules + compiled wrappers
    # (base_io_module would be your aereo core module with read/reproject/write)
    dr = (
        driver.Builder()
        # .with_modules(base_io_module)  # read, reproject, write
        .with_functions(list(compiled.values()))
        .build()
    )

    # Execute — Hamilton sees:
    #   raw_dataset -> step_0_filter_nan -> reprojected_dataset -> final_artifacts
    # filter_clouds and ndvi exist in the module but are not in the dependency
    # graph, so Hamilton does not run them.
    result = dr.execute(
        ["final_artifacts"],
        inputs={"vars_to_check": ["B04", "B08"]},
    )
    return result


# ---------------------------------------------------------------------------
# 4.  Advanced: conditional / branching pipelines
# ---------------------------------------------------------------------------
# If a user wants BOTH filter_clouds AND filter_nan, but on different
# branches (e.g., one for training data, one for validation), you compile
# two separate chains or use Hamilton's native branching.


def compile_branched_pipeline(
    steps_by_branch: dict[str, Sequence],
    plugin_functions: Mapping[str, Callable],
) -> dict[str, Callable]:
    """Compile multiple independent chains.

    Example config::

        {
            "train": ["filter_clouds", "ndvi"],
            "val":   ["filter_nan"],
        }
    """
    compiled: dict[str, Callable] = {}
    for branch_name, steps in steps_by_branch.items():
        branch_funcs = compile_pipeline(steps, plugin_functions)
        # rename outputs to avoid collisions
        for old_name, func in branch_funcs.items():
            new_name = f"{branch_name}_{old_name}"
            func.__name__ = new_name
            compiled[new_name] = func
    return compiled


# ---------------------------------------------------------------------------
# 5.  The bottom line
# ---------------------------------------------------------------------------
# - **Discovery** = what *can* run (Hamilton ``with_modules``).
# - **Config**    = what *does* run (your pipeline YAML / Python list).
# - **Compiler**  = how they connect (the ``compile_pipeline`` helper above).
#
# You do not lose control by adopting Hamilton.  You gain the ability to
# visualise, test, and cache every intermediate step while still deciding
# exactly which steps execute and in what order.
# ---------------------------------------------------------------------------
