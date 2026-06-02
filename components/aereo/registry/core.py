import importlib.metadata
from typing import Any, Dict, List, Sequence, Tuple, Type

# Importing the contracts we defined earlier
from aereo.interfaces import (
    Processor,
    Reader,
    Reprojector,
    SearchProvider,
    Writer,
)
from structlog import get_logger

logger = get_logger()


def _dump_params(params: Sequence[Any], detailed: bool) -> list[dict]:
    """Serialize PluginParam instances to JSON-safe dicts.

    Args:
        params: Sequence of PluginParam objects.
        detailed: When ``True``, each param includes all attributes.
            When ``False``, only ``name`` and ``default`` are returned.

    Returns:
        List of JSON-serializable dicts representing PluginParam.
    """
    if detailed:
        return [p.model_dump() for p in params]
    return [{"name": p.name, "default": p.default} for p in params]


class _TypedRegistry:
    """Internal helper that manages plugins of a single type.

    Encapsulates the collections, mappings, and lookup logic so that
    ``AereoRegistry`` does not have to duplicate state for every plugin type.
    """

    def __init__(self) -> None:
        self.plugins: Dict[str, Type] = {}
        self.collection_to_plugins: Dict[str, List[str]] = {}
        self.collection_mapping: Dict[str, Dict[str, str]] = {}

    def register(
        self,
        plugin_name: str,
        plugin_class: Type,
        original_collections: Dict[str, str],
    ) -> None:
        """Register a plugin and index its supported collections.

        Args:
            plugin_name: Entry-point name of the plugin.
            plugin_class: The plugin class to register.
            original_collections: Shared mapping of lowercase collection name to
                the first-seen original casing. Updated in-place.
        """
        self.plugins[plugin_name] = plugin_class

        plugin_canonical_map: Dict[str, str] = {}
        for product in plugin_class.supported_collections:
            lower_product = product.lower()
            self.collection_to_plugins.setdefault(lower_product, []).append(plugin_name)
            plugin_canonical_map[lower_product] = product
            if lower_product not in original_collections:
                original_collections[lower_product] = product

        self.collection_mapping[plugin_name] = plugin_canonical_map

    def find_for(self, collection_name: str, wildcard: str) -> List[str]:
        """Return plugin names supporting a collection, including wildcards.

        Args:
            collection_name: Name of the collection to query.
            wildcard: The wildcard token (e.g. "*").

        Returns:
            Sorted list of unique plugin names that support the collection.
        """
        lower_name = collection_name.lower()
        results = set(self.collection_to_plugins.get(lower_name, []))
        results.update(self.collection_to_plugins.get(wildcard, []))
        return sorted(results)

    def get_collections(self, plugin_name: str) -> List[str]:
        """Return the supported collections for a plugin.

        Args:
            plugin_name: Entry-point name of the plugin.

        Returns:
            List of collection strings supported by the plugin, or an empty list
            if the plugin is not known.
        """
        if plugin_name in self.plugins:
            return list(self.plugins[plugin_name].supported_collections)
        return []

    def has(self, plugin_name: str) -> bool:
        """Check whether a plugin with the given name is registered.

        Args:
            plugin_name: Entry-point name of the plugin.

        Returns:
            True if the plugin is registered, False otherwise.
        """
        return plugin_name in self.plugins

    def get_collection_mapping(
        self,
        plugin_name: str,
        collection_names: Sequence[str],
        wildcard: str,
    ) -> List[str]:
        """Map user-provided collection names to the plugin's declared format.

        Args:
            plugin_name: Name of the plugin.
            collection_names: Collection names provided by user (any case).
            wildcard: The wildcard token (e.g. "*").

        Returns:
            List of collection names mapped to the plugin's declared format.
        """
        if plugin_name not in self.collection_mapping:
            return [c.lower() for c in collection_names]

        canonical_to_original = self.collection_mapping[plugin_name]
        if wildcard in canonical_to_original:
            return list(collection_names)

        result = []
        for col in collection_names:
            canonical = col.lower()
            mapped = canonical_to_original.get(canonical, canonical)
            result.append(mapped)
        return result

    def get(self, plugin_name: str, plugin_type: str, **kwargs) -> Any:
        """Instantiate a plugin from the registry.

        Args:
            plugin_name: Entry-point name of the plugin.
            plugin_type: Human-readable plugin type for error messages.
            **kwargs: Configuration values passed to the plugin constructor.

        Returns:
            An instantiated plugin.

        Raises:
            ValueError: If the plugin name is not registered.
        """
        if plugin_name not in self.plugins:
            raise ValueError(
                f"{plugin_type} plugin '{plugin_name}' not found or failed to load."
            )
        return self.plugins[plugin_name](**kwargs)


class AereoRegistry:
    """Dynamically discovers and manages aereo plugins via Python entry_points.

    The registry is data-driven: adding a new plugin type requires one line in
    ``PLUGIN_TYPES`` and one new base class (see FR-5.1 / FR-5.2).
    """

    ENTRY_POINT_GROUP: str = "aereo.plugins"
    WILDCARD: str = "*"

    # prefix -> (type_label, base_class)
    PLUGIN_TYPES: Dict[str, Tuple[str, Type]] = {
        "search_": ("searcher", SearchProvider),
        "read_": ("reader", Reader),
        "reproject_": ("reprojector", Reprojector),
        "process_": ("processor", Processor),
        "write_": ("writer", Writer),
    }

    def __init__(self, auto_discover: bool = True) -> None:
        """Initialize the registry and optionally discover all installed plugins.

        Args:
            auto_discover: When ``True`` (default), scan entry points immediately.
                Set to ``False`` and call :meth:`discover_plugins` later if you
                want lazy loading, or pass pre-discovered plugins via
                :meth:`register_plugins`.
        """
        # One _TypedRegistry per plugin type
        self._registries: Dict[str, _TypedRegistry] = {
            label: _TypedRegistry() for label, _ in self.PLUGIN_TYPES.values()
        }

        # Expose the internal dicts directly so existing tests and consumers
        # that access ``_searchers`` continue to work.
        self._searchers: Dict[str, Type[SearchProvider]] = self._registries[
            "searcher"
        ].plugins  # type: ignore[assignment]

        # Track original case for display in list_supported_collections
        self._original_collections: Dict[str, str] = {}

        if auto_discover:
            self.discover_plugins()

    def _label_for(self, plugin_class: Type) -> str | None:
        """Return the registry label for a plugin class based on PLUGIN_TYPES."""
        for label, base_class in self.PLUGIN_TYPES.values():
            if issubclass(plugin_class, base_class):
                return label
        return None

    def register_plugins(self, plugins: Dict[str, Type]) -> None:
        """Register pre-discovered plugins without scanning entry points.

        This is useful in environments like AWS Lambda where entry point
        scanning is slow (~20-30s with many packages). Instead, import the
        plugin classes directly and register them explicitly.

        Args:
            plugins: Mapping of plugin name to plugin class.
        """
        for name, plugin_class in plugins.items():
            label = self._label_for(plugin_class)
            if label is not None:
                self._registries[label].register(
                    name, plugin_class, self._original_collections
                )

    def discover_plugins(self) -> None:
        """Finds all installed packages declaring aereo entry_points.

        Returns:
            None. Populates internal registries as a side effect.

        Raises:
            Exception: Individual plugin load failures are logged and swallowed
                so that one broken plugin does not prevent others from loading.
        """
        logger.info("Discovering aereo plugins...")

        # Load all plugins from the unified aereo.plugins group
        eps = importlib.metadata.entry_points(group=self.ENTRY_POINT_GROUP)
        for ep in eps:
            try:
                plugin_class = ep.load()
                label = self._label_for(plugin_class)

                if label is not None:
                    self._registries[label].register(
                        ep.name, plugin_class, self._original_collections
                    )
                    logger.debug(f"Loaded {label}: {ep.name}")
                else:
                    logger.warning(
                        f"Plugin '{ep.name}' does not inherit from any known base class. Skipping."
                    )
            except Exception as e:
                logger.error(
                    f"Failed to load plugin '{ep.name}': {e}",
                    exc_info=True,
                )

    # --- Generic API (FR-5.3) ---

    def find_for(self, type_label: str, collection_name: str) -> List[str]:
        """Return plugin names of *type_label* supporting *collection_name*.

        Args:
            type_label: Plugin type label (e.g. "searcher", "reader", "writer").
            collection_name: Name of the collection to query.

        Returns:
            Sorted list of plugin names that support the collection.
        """
        registry = self._registries.get(type_label)
        if registry is None:
            return []
        return registry.find_for(collection_name, self.WILDCARD)

    def get(self, type_label: str, plugin_name: str, **kwargs) -> Any:
        """Instantiate a plugin of *type_label* by *plugin_name*.

        Args:
            type_label: Plugin type label (e.g. "searcher", "reader").
            plugin_name: Entry-point name of the plugin.
            **kwargs: Configuration values passed to the plugin constructor.

        Returns:
            An instantiated plugin.

        Raises:
            ValueError: If the plugin type or name is not known.
        """
        registry = self._registries.get(type_label)
        if registry is None:
            raise ValueError(f"Unknown plugin type: {type_label}")
        return registry.get(plugin_name, type_label.capitalize(), **kwargs)

    def has(self, type_label: str, plugin_name: str) -> bool:
        """Check whether a plugin of *type_label* with *plugin_name* is registered.

        Args:
            type_label: Plugin type label.
            plugin_name: Entry-point name of the plugin.

        Returns:
            True if registered, False otherwise.
        """
        registry = self._registries.get(type_label)
        if registry is None:
            return False
        return registry.has(plugin_name)

    # --- Backward-compatible API ---

    def list_supported_collections(self) -> List[str]:
        """Returns a list of all products supported by currently installed plugins.

        Returns:
            Sorted list of collection names in their original case as defined
            by plugins.
        """
        all_products: set[str] = set()
        for registry in self._registries.values():
            all_products.update(registry.collection_to_plugins.keys())
        display_names = [self._original_collections.get(p, p) for p in all_products]
        return sorted(display_names)

    def find_searchers_for(self, collection_name: str) -> List[str]:
        """Returns names of search plugins that support the requested collection."""
        return self._registries["searcher"].find_for(collection_name, self.WILDCARD)

    def get_searcher_collections(self, plugin_name: str) -> List[str]:
        """Return the supported collections for a named search plugin."""
        return self._registries["searcher"].get_collections(plugin_name)

    def has_searcher(self, plugin_name: str) -> bool:
        """Check whether a search plugin with the given name is registered."""
        return self._registries["searcher"].has(plugin_name)

    def get_collection_mapping_for_searcher(
        self, plugin_name: str, collection_names: Sequence[str]
    ) -> List[str]:
        """Maps user-provided collection names to a specific search plugin's declared format."""
        return self._registries["searcher"].get_collection_mapping(
            plugin_name, collection_names, self.WILDCARD
        )

    def get_searcher(self, plugin_name: str, **kwargs) -> SearchProvider:
        """Instantiates and returns a SearchProvider by name."""
        return self._registries["searcher"].get(plugin_name, "Search", **kwargs)

    def get_plugin_params(
        self, plugin_name: str, *, detailed: bool = True
    ) -> dict[str, list[dict]]:
        """Return params metadata for any plugin (search or pipeline stage).

        Args:
            plugin_name: Entry-point name of the plugin.
            detailed: When ``True`` (default), each param includes all
                attributes (name, type, description, default, choices,
                required). When ``False``, only ``name`` and ``default``
                are returned.

        Returns:
            {"required": [...], "optional": [...]} where each item is a
            JSON-serializable dict representing a PluginParam.
        """
        cls: Type | None = None
        for registry in self._registries.values():
            cls = registry.plugins.get(plugin_name)
            if cls is not None:
                break

        if cls is None:
            raise KeyError(f"Unknown plugin: {plugin_name}")

        return {
            "required": _dump_params(cls.required_params, detailed),
            "optional": _dump_params(cls.optional_params, detailed),
        }

    def list_all_params(self, *, detailed: bool = True) -> dict[str, dict]:
        """JSON-serializable params catalog for all discovered plugins.

        Args:
            detailed: When ``True`` (default), each param includes all
                attributes. When ``False``, only ``name`` and ``default``
                are returned.

        Returns:
            Mapping of plugin name to a dict with keys ``type``, ``required``,
            and ``optional``. Each param list contains JSON-serializable dicts
            representing a PluginParam.
        """

        result: dict[str, dict] = {}
        for label, registry in self._registries.items():
            for name, cls in registry.plugins.items():
                result[name] = {
                    "type": label,
                    "required": _dump_params(cls.required_params, detailed),
                    "optional": _dump_params(cls.optional_params, detailed),
                }
        return result
