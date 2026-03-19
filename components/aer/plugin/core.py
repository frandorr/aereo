"""Core plugin registry and capability graph routing.

Provides a unified `@plugin` decorator and `PluginRegistry` that infers
type transitions (input -> output) from function annotations, building
a "Capability Graph" of all available data pipelines.
"""

from __future__ import annotations

import collections
import importlib.metadata
import inspect
from typing import (
    Any,
    Callable,
    TypeVar,
    get_type_hints,
)

from structlog import get_logger

logger = get_logger()


class PluginInfo:
    """Metadata about a registered plugin."""

    def __init__(
        self,
        name: str,
        category: str,
        func: Callable[..., Any],
        input_type: type[Any],
        return_type: type[Any],
    ):
        self.name = name
        self.category = category
        self.func = func
        self.input_type = input_type
        self.return_type = return_type

    def __repr__(self) -> str:
        in_name = getattr(self.input_type, "__name__", str(self.input_type))
        out_name = getattr(self.return_type, "__name__", str(self.return_type))
        return f"<Plugin '{self.name}' ({self.category}): {in_name} -> {out_name}>"

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)


class PluginRegistry:
    """A unified registry for all aer plugins that builds a capability graph."""

    _ENTRYPOINT_GROUP = "aer.plugins"

    def __init__(self) -> None:
        self.plugins: dict[tuple[str, str], PluginInfo] = {}
        self._plugins_loaded = False
        # Adjacency list: input_type -> list of (output_type, str)
        self.graph: dict[type[Any], list[tuple[type[Any], str]]] = (
            collections.defaultdict(list)
        )

    def _ensure_loaded(self) -> None:
        if self._plugins_loaded:
            return

        try:
            entry_points = importlib.metadata.entry_points(group=self._ENTRYPOINT_GROUP)
        except Exception as exc:
            logger.warning("failed_to_load_entrypoints", error=str(exc))
            return

        for entry in entry_points:
            try:
                # Loading the entry point should execute the module, triggering @plugin
                entry.load()
            except Exception as exc:
                logger.error("failed_to_load_plugin", plugin=entry.name, error=str(exc))

        self._plugins_loaded = True

    def register(self, name: str, category: str, func: Callable[..., Any]) -> None:
        """Registers a function as a plugin in the capability graph.

        The function must have type hints for its first argument (input) and return type.
        """
        key = (name, category)
        if key in self.plugins:
            if self.plugins[key].func is not func:
                raise ValueError(
                    f"Plugin '{name}' (category '{category}') is already registered with a different function."
                )
            return

        try:
            # get_type_hints evaluates string annotations if possible
            hints = get_type_hints(func)
        except Exception as exc:
            logger.warning(
                "plugin_type_hint_resolution_failed", plugin=name, error=str(exc)
            )
            hints = func.__annotations__

        signature = inspect.signature(func)
        params = list(signature.parameters.values())

        if not params:
            raise ValueError(
                f"Plugin '{name}' must take at least one argument (the input state)."
            )

        input_param_name = params[0].name
        input_type = hints.get(input_param_name, Any)
        return_type = hints.get("return", Any)

        info = PluginInfo(
            name=name,
            category=category,
            func=func,
            input_type=input_type,
            return_type=return_type,
        )
        self.plugins[(name, category)] = info
        self.graph[input_type].append((return_type, name))

        logger.debug(
            "plugin_registered",
            name=name,
            category=category,
            transition=f"{input_type} -> {return_type}",
        )

    def get(self, name: str, category: str | None = None) -> PluginInfo:
        """Retrieve a registered plugin by name and optionally category."""
        self._ensure_loaded()

        if category is not None:
            if (name, category) not in self.plugins:
                raise KeyError(
                    f"Plugin '{name}' (category '{category}') is not registered."
                )
            return self.plugins[(name, category)]

        matches = [p for (n, c), p in self.plugins.items() if n == name]
        if not matches:
            raise KeyError(f"Plugin '{name}' is not registered.")
        if len(matches) > 1:
            categories = [p.category for p in matches]
            raise KeyError(
                f"Multiple plugins found with name '{name}' under categories {categories}. "
                "Please specify a category."
            )
        return matches[0]

    def all(self) -> list[PluginInfo]:
        """Return all registered plugins."""
        self._ensure_loaded()
        return list(self.plugins.values())

    def show_capabilities(
        self,
        start_type: type[Any],
        depth: int = 0,
        indent: str = "",
        _visited: set[type[Any]] | None = None,
    ) -> None:
        """Print a textual tree of possible type transitions starting from start_type."""
        self._ensure_loaded()

        if _visited is None:
            _visited = set()

        type_name = getattr(start_type, "__name__", str(start_type))
        if depth == 0:
            print(f"[*] {type_name}")

        if start_type in _visited:
            return
        _visited.add(start_type)

        edges = self.graph.get(start_type, [])
        for i, (out_type, plugin_name) in enumerate(edges):
            is_last = i == len(edges) - 1
            marker = "└──" if is_last else "├──"
            out_name = getattr(out_type, "__name__", str(out_type))

            print(f"{indent} {marker} ({plugin_name}) -> {out_name}")

            next_indent = indent + ("     " if is_last else " │   ")
            self.show_capabilities(
                out_type,
                depth=depth + 1,
                indent=next_indent,
                _visited=_visited.copy(),
            )


# The global singleton instance
plugin_registry = PluginRegistry()

F = TypeVar("F", bound=Callable[..., Any])


def plugin(name: str, category: str) -> Callable[[F], F]:
    """Decorator to register a plugin.

    Usage::

        @plugin(name="my_plugin", category="search")
        def my_search(query: SearchQuery) -> gpd.GeoDataFrame:
            ...
    """

    def decorator(func: F) -> F:
        plugin_registry.register(name, category, func)
        return func

    return decorator


def _is_typed(tp: object) -> bool:
    """Return True if *tp* is a concrete type (not ``typing.Any``)."""
    return tp != Any


class Pipeline:
    """A sequence of plugins forming a type-safe data transition path."""

    def __init__(self, *plugin_refs: str | tuple[str, str]) -> None:
        self.plugin_refs = plugin_refs
        self.steps: list[PluginInfo] = []
        self._validate()

    def _validate(self) -> None:
        # Load all plugins
        plugin_registry._ensure_loaded()

        if not self.plugin_refs:
            return

        # Fetch all step infos
        for ref in self.plugin_refs:
            if isinstance(ref, tuple):
                self.steps.append(plugin_registry.get(*ref))
            else:
                self.steps.append(plugin_registry.get(ref))

        # Validate type transitions between steps, allowing `Any` as a flexible fallback
        for i in range(len(self.steps) - 1):
            curr_step = self.steps[i]
            next_step = self.steps[i + 1]

            curr_out = curr_step.return_type
            next_in = next_step.input_type

            # Exact match or Any — skip check when either side is untyped
            if _is_typed(curr_out) and _is_typed(next_in) and curr_out != next_in:
                try:
                    is_sub = issubclass(curr_out, next_in)
                except TypeError:
                    # Not real classes (e.g., Union, list[...]) — warn rather than crash
                    if curr_out != next_in:
                        logger.warning(
                            "pipeline_type_check_uncertain",
                            curr_step=curr_step.name,
                            next_step=next_step.name,
                            curr_out=str(curr_out),
                            next_in=str(next_in),
                        )
                else:
                    if not is_sub:
                        raise TypeError(
                            f"Pipeline type mismatch! Plugin '{curr_step.name}' returns {curr_out}, "
                            f"but plugin '{next_step.name}' expects {next_in}."
                        )

    def run(self, initial_input: Any, **kwargs: Any) -> Any:
        """Execute the pipeline sequentially."""
        data = initial_input
        # First step might take extra kwargs like max_concurrent depending on the plugin
        if self.steps:
            data = self.steps[0](data, **kwargs)

        for step in self.steps[1:]:
            data = step(data)

        return data


def run_search(plugin_name: str, query: Any, **kwargs: Any) -> Any:
    """Run a search plugin by name and return results.

    Looks up the plugin registered under category ``"search"`` and invokes it
    with the given *query* and any extra keyword arguments.

    Parameters
    ----------
    plugin_name:
        Name the plugin was registered with (e.g. ``"aws-goes"``).
    query:
        A :class:`SearchQuery` (or compatible) object.
    **kwargs:
        Forwarded to the plugin function.

    Returns
    -------
    geopandas.GeoDataFrame
        Search results conforming to :class:`SearchResultSchema`.
    """
    info = plugin_registry.get(plugin_name, "search")
    return info(query, **kwargs)


def run_extract(
    plugin_name: str,
    gdf: Any,
    output_dir: str,
    **kwargs: Any,
) -> Any:
    """Run an extract plugin by name on search results.

    Looks up the plugin registered under category ``"extract"`` and invokes it
    with the given GeoDataFrame, output directory, and any extra keyword
    arguments.

    Parameters
    ----------
    plugin_name:
        Name the plugin was registered with (e.g. ``"aws-goes"``).
    gdf:
        A GeoDataFrame conforming to :class:`SearchResultSchema`.
    output_dir:
        Directory (local path or S3 prefix) where extracted files are written.
    **kwargs:
        Forwarded to the plugin function.

    Returns
    -------
    geopandas.GeoDataFrame
        Extraction results conforming to :class:`ExtractedResultSchema`.
    """
    info = plugin_registry.get(plugin_name, "extract")
    return info(gdf, output_dir, **kwargs)
