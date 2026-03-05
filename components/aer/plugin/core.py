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
    Dict,
    List,
    Type,
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
        input_type: Type[Any],
        return_type: Type[Any],
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
        self.plugins: Dict[str, PluginInfo] = {}
        self._plugins_loaded = False
        # Adjacency list: input_type -> list of (output_type, plugin_name)
        self.graph: Dict[Type[Any], List[tuple[Type[Any], str]]] = (
            collections.defaultdict(list)
        )

    def _ensure_loaded(self) -> None:
        if self._plugins_loaded:
            return

        self._plugins_loaded = True
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

    def register(self, name: str, category: str, func: Callable[..., Any]) -> None:
        """Registers a function as a plugin in the capability graph.

        The function must have type hints for its first argument (input) and return type.
        """
        if name in self.plugins:
            if self.plugins[name].func is not func:
                raise ValueError(
                    f"Plugin '{name}' is already registered with a different function."
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
        self.plugins[name] = info
        self.graph[input_type].append((return_type, name))

        logger.debug(
            "plugin_registered",
            name=name,
            category=category,
            transition=f"{input_type} -> {return_type}",
        )

    def get(self, name: str) -> PluginInfo:
        """Retrieve a registered plugin by name."""
        self._ensure_loaded()
        if name not in self.plugins:
            raise KeyError(f"Plugin '{name}' is not registered.")
        return self.plugins[name]

    def all(self) -> List[PluginInfo]:
        """Return all registered plugins."""
        self._ensure_loaded()
        return list(self.plugins.values())

    def show_capabilities(
        self, start_type: Type[Any], depth: int = 0, indent: str = ""
    ) -> None:
        """Print a textual tree of possible type transitions starting from start_type."""
        self._ensure_loaded()

        type_name = getattr(start_type, "__name__", str(start_type))
        if depth == 0:
            print(f"[*] {type_name}")

        edges = self.graph.get(start_type, [])
        for i, (out_type, plugin_name) in enumerate(edges):
            is_last = i == len(edges) - 1
            marker = "└──" if is_last else "├──"
            out_name = getattr(out_type, "__name__", str(out_type))

            print(f"{indent} {marker} ({plugin_name}) -> {out_name}")

            next_indent = indent + ("     " if is_last else " │   ")
            self.show_capabilities(out_type, depth=depth + 1, indent=next_indent)


# The global singleton instance
plugin_registry = PluginRegistry()

F = TypeVar("F", bound=Callable[..., Any])


def plugin(name: str, category: str) -> Callable[[F], F]:
    """Decorator to register a plugin."""

    def decorator(func: F) -> F:
        plugin_registry.register(name, category, func)
        return func

    return decorator


class Pipeline:
    """A sequence of plugins forming a type-safe data transition path."""

    def __init__(self, *plugin_names: str) -> None:
        self.plugin_names = plugin_names
        self.steps: List[PluginInfo] = []
        self._validate()

    def _validate(self) -> None:
        # Load all plugins
        plugin_registry._ensure_loaded()

        if not self.plugin_names:
            return

        # Fetch all step infos
        for name in self.plugin_names:
            self.steps.append(plugin_registry.get(name))

        # Validate type transitions between steps, allowing `Any` as a flexible fallback
        for i in range(len(self.steps) - 1):
            curr_step = self.steps[i]
            next_step = self.steps[i + 1]

            curr_out = curr_step.return_type
            next_in = next_step.input_type

            # Exact match or Any
            if curr_out is not Any and next_in is not Any and curr_out != next_in:
                # In Python's typing, strict equality is sometimes too harsh (e.g., subclasses)
                # For simplicity in this graph, we start with strict equality where annotated,
                # but an advanced version could use issubclass.
                try:
                    if not issubclass(curr_out, next_in):
                        raise TypeError(
                            f"Pipeline type mismatch! Plugin '{curr_step.name}' returns {curr_out}, "
                            f"but plugin '{next_step.name}' expects {next_in}."
                        )
                except Exception:
                    # In case they aren't classes (e.g., Union, list[...])
                    if curr_out != next_in:
                        logger.warning(
                            "pipeline_type_check_uncertain",
                            curr_step=curr_step.name,
                            next_step=next_step.name,
                            curr_out=str(curr_out),
                            next_in=str(next_in),
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
