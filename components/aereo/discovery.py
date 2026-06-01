"""Per-stage plugin discovery for Hamilton-based AEREO pipelines.

Discovers function-based plugins via Python entry-point groups
(e.g. ``aereo.search``, ``aereo.read``, ``aereo.process``).
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
from types import ModuleType
from typing import Mapping

from structlog import get_logger

logger = get_logger()

WILDCARD: str = "*"


class StagePlugins:
    """Holds discovered plugins for a single stage.

    Attributes:
        name_to_module: Mapping of plugin entry-point name to loaded module.
        collection_to_names: Mapping of lower-cased collection name to list of
            plugin names that support it.
        name_to_collections: Mapping of plugin name to the collections it supports.
    """

    def __init__(self) -> None:
        self.name_to_module: dict[str, ModuleType] = {}
        self.collection_to_names: dict[str, list[str]] = {}
        self.name_to_collections: dict[str, tuple[str, ...]] = {}
        self._original_collections: dict[str, str] = {}

    def register(self, name: str, module: ModuleType) -> None:
        """Register a plugin module by name.

        Reads ``supported_collections`` from the module (defaulting to an empty
        tuple). Collections are indexed case-insensitively.

        Args:
            name: Entry-point name of the plugin.
            module: The plugin module.
        """
        self.name_to_module[name] = module

        collections = getattr(module, "supported_collections", ())
        if not isinstance(collections, (list, tuple)):
            collections = (collections,)

        self.name_to_collections[name] = tuple(collections)

        for collection in collections:
            lower = collection.lower()
            self.collection_to_names.setdefault(lower, []).append(name)
            if lower not in self._original_collections:
                self._original_collections[lower] = collection

    def list_supported_collections(self) -> list[str]:
        """Return all collections supported by discovered plugins.

        Returns:
            Sorted list of collection names in their original casing.
        """
        display_names = [
            self._original_collections.get(c, c) for c in self.collection_to_names
        ]
        return sorted(display_names)


def discover_plugins(group: str) -> StagePlugins:
    """Discover plugins for a given entry-point group.

    Args:
        group: The entry-point group to scan (e.g. ``"aereo.search"``).

    Returns:
        A :class:`StagePlugins` instance populated with discovered plugins.
    """
    result = StagePlugins()
    try:
        eps = importlib.metadata.entry_points(group=group)
    except TypeError:
        # Python < 3.10 compatibility
        eps = importlib.metadata.entry_points().get(group, [])  # type: ignore[union-attr]

    for ep in eps:
        try:
            loaded = ep.load()
            # If entry point resolves to a module, use it directly.
            # If it resolves to a class/function, get its containing module.
            if isinstance(loaded, ModuleType):
                module = loaded
            elif hasattr(loaded, "__module__"):
                module = importlib.import_module(loaded.__module__)
            else:
                logger.warning(
                    f"Plugin '{ep.name}' in {group} is not a module and has no "
                    f"__module__. Skipping."
                )
                continue

            result.register(ep.name, module)
            logger.debug(f"Loaded {group}: {ep.name}")
        except Exception as e:
            logger.error(
                f"Failed to load plugin '{ep.name}' from {group}: {e}",
                exc_info=True,
            )

    return result


def resolve_plugin(
    stage: str,
    collection: str,
    plugin_hints: Mapping[str, str],
    stage_plugins: StagePlugins,
) -> ModuleType:
    """Resolve which plugin module to use for a stage.

    Resolution priority:

    1. ``plugin_hints[stage]`` — explicit user choice.
    2. Collection match — auto-discovery via ``supported_collections``.
    3. Wildcard fallback — a plugin declaring ``supported_collections = ("*",)``.

    Args:
        stage: The pipeline stage (e.g. ``"search"``, ``"read"``).
        collection: The collection name to resolve for.
        plugin_hints: Mapping of stage name to explicit plugin name.
        stage_plugins: Discovered plugins for this stage.

    Returns:
        The resolved plugin module.

    Raises:
        ValueError: If no plugin can be resolved.
    """
    hint = plugin_hints.get(stage)
    if hint is not None:
        if hint in stage_plugins.name_to_module:
            return stage_plugins.name_to_module[hint]
        raise ValueError(
            f"Plugin hint '{hint}' for stage '{stage}' not found among "
            f"discovered plugins: {sorted(stage_plugins.name_to_module)}."
        )

    lower_collection = collection.lower()
    names = stage_plugins.collection_to_names.get(lower_collection, [])
    if names:
        return stage_plugins.name_to_module[names[0]]

    wildcard_names = stage_plugins.collection_to_names.get(WILDCARD, [])
    if wildcard_names:
        return stage_plugins.name_to_module[wildcard_names[0]]

    raise ValueError(
        f"No plugin found for stage '{stage}' and collection '{collection}'. "
        f"Discovered collections: {stage_plugins.list_supported_collections()}."
    )
