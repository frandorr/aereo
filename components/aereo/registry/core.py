import importlib.metadata
from typing import Any, Dict, List, Sequence, Type

# Importing the contracts we defined earlier
from aereo.interfaces import Extractor, SearchProvider
from structlog import get_logger

logger = get_logger()


class _TypedRegistry:
    """Internal helper that manages plugins of a single type.

    Encapsulates the collections, mappings, and lookup logic so that
    ``AereoRegistry`` does not have to duplicate state for searchers and
    extractors.
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
    """
    Dynamically discovers and manages aereo plugins via Python entry_points.
    """

    ENTRY_POINT_GROUP: str = "aereo.plugins"
    WILDCARD: str = "*"

    def __init__(self) -> None:
        """Initialize the registry and discover all installed plugins."""
        self._searcher_registry = _TypedRegistry()
        self._extractor_registry = _TypedRegistry()
        # Expose the internal dicts directly so existing tests and consumers
        # that access ``_searchers`` / ``_extractors`` continue to work.
        self._searchers: Dict[str, Type[SearchProvider]] = (
            self._searcher_registry.plugins  # type: ignore[assignment]
        )
        self._extractors: Dict[str, Type[Extractor]] = self._extractor_registry.plugins  # type: ignore[assignment]

        # Track original case for display in list_supported_collections
        self._original_collections: Dict[str, str] = {}

        # Automatically load on instantiation
        self.discover_plugins()

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

                if issubclass(plugin_class, SearchProvider):
                    self._searcher_registry.register(
                        ep.name, plugin_class, self._original_collections
                    )
                    logger.debug(f"Loaded searcher: {ep.name}")
                elif issubclass(plugin_class, Extractor):
                    self._extractor_registry.register(
                        ep.name, plugin_class, self._original_collections
                    )
                    logger.debug(f"Loaded extractor: {ep.name}")
                else:
                    logger.warning(
                        f"Plugin '{ep.name}' does not inherit from SearchProvider or Extractor. Skipping."
                    )
            except Exception as e:
                logger.error(
                    f"Failed to load plugin '{ep.name}': {e}",
                    exc_info=True,
                )

    # --- Public API for the CLI / Orchestrator ---

    def list_supported_collections(self) -> List[str]:
        """Returns a list of all products supported by currently installed plugins.

        Returns:
            Sorted list of collection names in their original case as defined
            by plugins.
        """
        # Combine keys from both maps and return unique values in original case
        all_products = set(self._searcher_registry.collection_to_plugins.keys()).union(
            set(self._extractor_registry.collection_to_plugins.keys())
        )
        # Map back to original case for display
        display_names = [self._original_collections.get(p, p) for p in all_products]
        return sorted(display_names)

    def find_searchers_for(self, collection_name: str) -> List[str]:
        """Returns names of search plugins that support the requested collection.

        Case-insensitive lookup. Wildcard plugins (supported_collections=["*"])
        are returned for any collection.

        Args:
            collection_name: Name of the collection to query.

        Returns:
            Sorted list of plugin names that support the collection.
        """
        return self._searcher_registry.find_for(collection_name, self.WILDCARD)

    def find_extractors_for(self, collection_name: str) -> List[str]:
        """Returns names of extraction plugins that support the requested collection.

        Case-insensitive lookup. Wildcard plugins (supported_collections=["*"])
        are returned for any collection.

        Args:
            collection_name: Name of the collection to query.

        Returns:
            Sorted list of plugin names that support the collection.
        """
        return self._extractor_registry.find_for(collection_name, self.WILDCARD)

    def get_searcher_collections(self, plugin_name: str) -> List[str]:
        """Return the supported collections for a named search plugin.

        Args:
            plugin_name: Entry-point name of the search plugin.

        Returns:
            List of collection strings supported by the plugin, or an empty list
            if the plugin is not known.
        """
        return self._searcher_registry.get_collections(plugin_name)

    def get_extractor_collections(self, plugin_name: str) -> List[str]:
        """Return the supported collections for a named extractor plugin.

        Args:
            plugin_name: Entry-point name of the extractor plugin.

        Returns:
            List of collection strings supported by the plugin, or an empty list
            if the plugin is not known.
        """
        return self._extractor_registry.get_collections(plugin_name)

    def has_searcher(self, plugin_name: str) -> bool:
        """Check whether a search plugin with the given name is registered.

        Args:
            plugin_name: Entry-point name of the plugin.

        Returns:
            True if the plugin is registered, False otherwise.
        """
        return self._searcher_registry.has(plugin_name)

    def has_extractor(self, plugin_name: str) -> bool:
        """Check whether an extractor plugin with the given name is registered.

        Args:
            plugin_name: Entry-point name of the plugin.

        Returns:
            True if the plugin is registered, False otherwise.
        """
        return self._extractor_registry.has(plugin_name)

    def get_collection_mapping_for_searcher(
        self, plugin_name: str, collection_names: Sequence[str]
    ) -> List[str]:
        """Maps user-provided collection names to a specific search plugin's declared format.

        Takes user-provided collection names (in any case) and maps them to the exact case
        that the specified plugin declared in its supported_collections.

        Args:
            plugin_name: Name of the search plugin
            collection_names: Collection names provided by user (any case)

        Returns:
            List of collection names mapped to the plugin's declared format

        Example:
            # Plugin declares supported_collections=["abi-l1b-radc"]
            # User searches with "ABI-L1b-RadC"
            # This method returns ["abi-l1b-radc"]
        """
        return self._searcher_registry.get_collection_mapping(
            plugin_name, collection_names, self.WILDCARD
        )

    def get_collection_mapping_for_extractor(
        self, plugin_name: str, collection_names: Sequence[str]
    ) -> List[str]:
        """Maps user-provided collection names to a specific extractor plugin's declared format.

        Takes user-provided collection names (in any case) and maps them to the exact case
        that the specified plugin declared in its supported_collections.

        Args:
            plugin_name: Name of the extractor plugin
            collection_names: Collection names provided by user (any case)

        Returns:
            List of collection names mapped to the plugin's declared format

        Example:
            # Plugin declares supported_collections=["goes-16"]
            # User searches with "GOES-16"
            # This method returns ["goes-16"]
        """
        return self._extractor_registry.get_collection_mapping(
            plugin_name, collection_names, self.WILDCARD
        )

    def get_searcher(self, plugin_name: str, **kwargs) -> SearchProvider:
        """Instantiates and returns a SearchProvider by name.

        Args:
            plugin_name: Entry-point name of the search plugin.
            **kwargs: Configuration values passed to the plugin constructor.

        Returns:
            An instantiated SearchProvider.

        Raises:
            ValueError: If the plugin name is not registered.
        """
        return self._searcher_registry.get(plugin_name, "Search", **kwargs)

    def get_extractor(self, plugin_name: str, **kwargs) -> Extractor:
        """Instantiates and returns an Extractor by name.

        Args:
            plugin_name: Entry-point name of the extractor plugin.
            **kwargs: Configuration values passed to the plugin constructor.

        Returns:
            An instantiated Extractor.

        Raises:
            ValueError: If the plugin name is not registered.
        """
        return self._extractor_registry.get(plugin_name, "Extractor", **kwargs)

    def get_plugin_params(self, plugin_name: str) -> dict[str, list[dict]]:
        """Return params metadata for any plugin (search or extract).

        Args:
            plugin_name: Entry-point name of the plugin.

        Returns:
            {"required": [...], "optional": [...]} where each item is a
            JSON-serializable dict representing a PluginParam.
        """
        cls = self._searchers.get(plugin_name) or self._extractors.get(plugin_name)
        if cls is None:
            raise KeyError(f"Unknown plugin: {plugin_name}")
        return {
            "required": [p.model_dump() for p in cls.required_params],
            "optional": [p.model_dump() for p in cls.optional_params],
        }

    def list_all_params(self) -> dict[str, dict]:
        """JSON-serializable params catalog for all discovered plugins.

        Returns:
            Mapping of plugin name to a dict with keys ``type`` ("search" or
            "extract"), ``required``, and ``optional``. Each param list contains
            JSON-serializable dicts representing a PluginParam.
        """
        from aereo.interfaces import PluginParam

        def _dump(params: tuple[PluginParam, ...]) -> list[dict]:
            return [p.model_dump() for p in params]

        return {
            name: {
                "type": "search" if name in self._searchers else "extract",
                "required": _dump(cls.required_params),
                "optional": _dump(cls.optional_params),
            }
            for name, cls in {**self._searchers, **self._extractors}.items()
        }
