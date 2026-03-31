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
        plugin_class: type[Any],
        input_type: type[Any],
        return_type: type[Any],
    ):
        self.name = name
        self.category = category
        self.plugin_class = plugin_class
        self.input_type = input_type
        self.return_type = return_type

    def __repr__(self) -> str:
        in_name = getattr(self.input_type, "__name__", str(self.input_type))
        out_name = getattr(self.return_type, "__name__", str(self.return_type))
        return f"<Plugin '{self.name}' ({self.category}): {in_name} -> {out_name}>"

    def instantiate(self, *args: Any, **kwargs: Any) -> Any:
        """Instantiate the plugin class and return the instance."""
        return self.plugin_class(*args, **kwargs)


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

    def _resolve_method(
        self, plugin_class: type[Any], category: str
    ) -> Callable[..., Any]:
        """Resolve the method to inspect for type hints based on category."""
        method_name = category
        method = getattr(plugin_class, method_name, None)
        if method is not None:
            return method

        for fallback in ("__call__", "execute", "run"):
            method = getattr(plugin_class, fallback, None)
            if method is not None:
                return method

        raise ValueError(
            f"Plugin class {plugin_class.__name__} has no method matching "
            f"category '{category}' or any fallback (__call__, execute, run)."
        )

    def register(self, name: str, category: str, plugin_class: type[Any]) -> None:
        """Registers a class as a plugin in the capability graph.

        The class must have a method matching the category name (or a fallback
        like __call__, execute, run) with type hints for its first argument (input)
        and return type.
        """
        key = (name, category)
        if key in self.plugins:
            if self.plugins[key].plugin_class is not plugin_class:
                raise ValueError(
                    f"Plugin '{name}' (category '{category}') is already registered with a different class."
                )
            return

        method = self._resolve_method(plugin_class, category)

        try:
            hints = get_type_hints(method)
        except Exception as exc:
            logger.warning(
                "plugin_type_hint_resolution_failed", plugin=name, error=str(exc)
            )
            hints = method.__annotations__

        signature = inspect.signature(method)
        params = list(signature.parameters.values())

        if not params:
            raise ValueError(
                f"Plugin '{name}' method must take at least one argument (the input state)."
            )

        input_param_name = params[0].name
        input_type = hints.get(input_param_name, Any)
        return_type = hints.get("return", Any)

        info = PluginInfo(
            name=name,
            category=category,
            plugin_class=plugin_class,
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

T = TypeVar("T", bound=type[Any])


def plugin(name: str, category: str) -> Callable[[T], T]:
    """Decorator to register a class-based plugin.

    Usage::

        @plugin(name="my_plugin", category="search")
        class MySearchPlugin:
            def search(self, query: SearchQuery) -> gpd.GeoDataFrame:
                ...
    """

    def decorator(cls: T) -> T:
        plugin_registry.register(name, category, cls)
        return cls

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
        for step in self.steps:
            instance = step.instantiate()
            method = getattr(instance, step.category, None)
            if method is None:
                method = getattr(instance, "__call__", None)
            if method is None:
                method = getattr(instance, "execute", None)
            if method is None:
                raise AttributeError(
                    f"Plugin '{step.name}' has no callable method for category '{step.category}'."
                )
            data = method(data, **kwargs)
            kwargs = {}

        return data


def run_search(plugin_name: str, query: Any, **kwargs: Any) -> Any:
    """Run a search plugin by name and return results.

    Looks up the plugin registered under category ``"search"``, instantiates
    the class, and invokes its ``search`` method with the given *query* and
    any extra keyword arguments.

    Parameters
    ----------
    plugin_name:
        Name the plugin was registered with (e.g. ``"aws-goes"``).
    query:
        A :class:`SearchQuery` (or compatible) object.
    **kwargs:
        Forwarded to the plugin method.

    Returns
    -------
    geopandas.GeoDataFrame
        Search results conforming to :class:`SearchResultSchema`.
    """
    info = plugin_registry.get(plugin_name, "search")
    instance = info.instantiate()
    method = getattr(instance, "search", None)
    if method is None:
        method = getattr(instance, "__call__", None)
    if method is None:
        method = getattr(instance, "execute", None)
    if method is None:
        raise AttributeError(f"Search plugin '{plugin_name}' has no callable method.")
    return method(query, **kwargs)


def run_extract(
    plugin_name: str,
    gdf: Any,
    output_dir: str,
    **kwargs: Any,
) -> Any:
    """Run an extract plugin by name on search results.

    Looks up the plugin registered under category ``"extract"``, instantiates
    the class, and invokes its ``extract`` method with the given GeoDataFrame,
    output directory, and any extra keyword arguments.

    Parameters
    ----------
    plugin_name:
        Name the plugin was registered with (e.g. ``"aws-goes"``).
    gdf:
        A GeoDataFrame conforming to :class:`SearchResultSchema`.
    output_dir:
        Directory (local path or S3 prefix) where extracted files are written.
    **kwargs:
        Forwarded to the plugin method.

    Returns
    -------
    geopandas.GeoDataFrame
        Extraction results conforming to :class:`ExtractedResultSchema`.
    """
    info = plugin_registry.get(plugin_name, "extract")
    instance = info.instantiate()
    method = getattr(instance, "extract", None)
    if method is None:
        method = getattr(instance, "__call__", None)
    if method is None:
        method = getattr(instance, "execute", None)
    if method is None:
        raise AttributeError(f"Extract plugin '{plugin_name}' has no callable method.")
    return method(gdf, output_dir, **kwargs)
