"""Compile processor config into Hamilton-compatible functions.

Turns declarative processor lists (sequential and parallel) into a dict of
functions that Hamilton can wire into a DAG.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Mapping, Sequence


def _make_sequential_wrapper(
    func: Callable[[Any], Any],
    name: str,
    input_name: str,
) -> Callable[[Any], Any]:
    """Create a Hamilton node that applies *func* sequentially.

    Args:
        func: The processor function to wrap.
        name: The node name in the Hamilton DAG.
        input_name: The upstream node name to depend on.

    Returns:
        A function with signature ``name(input_name) -> Any``.
    """

    @functools.wraps(func)
    def _inner(ds: Any) -> Any:
        return func(ds)

    code = compile(
        f"def {name}({input_name}):\n    return __inner({input_name})\n",
        "<compiler>",
        "exec",
    )
    namespace: dict[str, Any] = {"__inner": _inner}
    exec(code, namespace)
    return namespace[name]


def _make_parallel_wrapper(
    func: Callable[[Any], Any],
    name: str,
    input_name: str,
) -> Callable[[Any], Any]:
    """Create a Hamilton node that applies *func* on a parallel branch.

    Args:
        func: The processor function to wrap.
        name: The node name in the Hamilton DAG.
        input_name: The upstream node name to depend on.

    Returns:
        A function with signature ``name(input_name) -> Any``.
    """

    @functools.wraps(func)
    def _inner(ds: Any) -> Any:
        return func(ds)

    code = compile(
        f"def {name}({input_name}):\n    return __inner({input_name})\n",
        "<compiler>",
        "exec",
    )
    namespace: dict[str, Any] = {"__inner": _inner}
    exec(code, namespace)
    return namespace[name]


def _make_merge_wrapper(
    branch_names: Sequence[str],
    input_name: str,
    name: str,
) -> Callable[..., tuple[Any, ...]]:
    """Create a Hamilton node that merges parallel branch outputs.

    Args:
        branch_names: Names of the upstream parallel branch nodes.
        input_name: The upstream node name that fed the parallel branches.
            Included for symmetry but not exposed as a parameter so that
            Hamilton does not require an extra dependency edge.
        name: The node name in the Hamilton DAG.

    Returns:
        A function with signature ``name(*branch_names) -> tuple[Any, ...]``.
    """
    del input_name  # Not used as a parameter; parallel branches already consume it.

    def _inner(*args: Any) -> tuple[Any, ...]:
        return args

    params = ", ".join(branch_names)
    code = compile(
        f"def {name}({params}):\n    return __inner({params})\n",
        "<compiler>",
        "exec",
    )
    namespace: dict[str, Any] = {"__inner": _inner}
    exec(code, namespace)
    return namespace[name]


def compile_processors(
    config: Sequence[str | dict[str, Any]],
    plugin_functions: Mapping[str, Callable[[Any], Any]],
) -> dict[str, Callable[..., Any]]:
    """Compile processor config into Hamilton-compatible functions.

    Config formats:

    * Sequential: ``["mask_clouds", "normalize"]``
    * Parallel: ``[{"parallel": ["compute_ndvi", "compute_ndwi"]}]``
    * With params: ``[{"mask_clouds": {"threshold": 0.5}}]`` (params are
      ignored by the compiler; they are resolved via profile stage params).

    Args:
        config: Declarative processor pipeline.
        plugin_functions: Mapping from processor name to callable.

    Returns:
        A dictionary of function-name → function ready for Hamilton.

    Raises:
        ValueError: If a processor in *config* is not found in
            *plugin_functions*.
    """
    compiled: dict[str, Callable[..., Any]] = {}
    prev_output = "read_scenes"

    for idx, step in enumerate(config):
        if isinstance(step, dict) and "parallel" in step:
            parallel_names: list[str] = []
            for proc_name in step["parallel"]:
                if proc_name not in plugin_functions:
                    raise ValueError(
                        f"Processor {proc_name!r} not found in plugin functions. "
                        f"Available: {sorted(plugin_functions.keys())}"
                    )
                func = plugin_functions[proc_name]
                wrapper_name = f"parallel_{idx}_{proc_name}"
                compiled[wrapper_name] = _make_parallel_wrapper(
                    func, wrapper_name, prev_output
                )
                parallel_names.append(wrapper_name)

            merge_name = f"merge_{idx}"
            compiled[merge_name] = _make_merge_wrapper(
                parallel_names, prev_output, merge_name
            )
            prev_output = merge_name
        else:
            if isinstance(step, str):
                proc_name = step
            else:
                # dict with params, e.g. {"mask_clouds": {"threshold": 0.5}}
                proc_name = next(iter(step.keys()))

            if proc_name not in plugin_functions:
                raise ValueError(
                    f"Processor {proc_name!r} not found in plugin functions. "
                    f"Available: {sorted(plugin_functions.keys())}"
                )
            func = plugin_functions[proc_name]
            wrapper_name = f"step_{idx}_{proc_name}"
            compiled[wrapper_name] = _make_sequential_wrapper(
                func, wrapper_name, prev_output
            )
            prev_output = wrapper_name

    return compiled
