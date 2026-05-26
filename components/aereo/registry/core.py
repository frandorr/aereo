import importlib.metadata
from typing import Dict, List, Sequence, Type

# Importing the contracts we defined earlier
from aereo.interfaces import Extractor, SearchProvider
from structlog import get_logger

logger = get_logger()


class AereoRegistry:
    """
    Dynamically discovers and manages aereo plugins via Python entry_points.
    """

    def __init__(self):
        # Store the class definitions, not instantiated objects
        self._searchers: Dict[str, Type[SearchProvider]] = {}
        self._extractors: Dict[str, Type[Extractor]] = {}

        # Fast-lookup maps: collection -> list of plugin names
        self._collection_to_searchers: Dict[str, List[str]] = {}
        self._collection_to_extractors: Dict[str, List[str]] = {}

        # Track original case for display in list_supported_collections
        self._original_collections: Dict[str, str] = {}

        # Per-plugin mapping: plugin_name -> {canonical_name -> original_name}
        # This allows mapping user's collection name to plugin's declared format
        self._searcher_collection_mapping: Dict[str, Dict[str, str]] = {}
        self._extractor_collection_mapping: Dict[str, Dict[str, str]] = {}

        # Automatically load on instantiation
        self.discover_plugins()

    def discover_plugins(self) -> None:
        """Finds all installed packages declaring aereo entry_points."""
        logger.info("Discovering aereo plugins...")

        # Load all plugins from the unified aereo.plugins group
        eps = importlib.metadata.entry_points(group="aereo.plugins")
        for ep in eps:
            try:
                plugin_class = ep.load()

                if issubclass(plugin_class, SearchProvider):
                    self._searchers[ep.name] = plugin_class
                    self._map_products(
                        ep.name,
                        plugin_class,
                        self._collection_to_searchers,
                        self._searcher_collection_mapping,
                    )
                    logger.debug(f"Loaded searcher: {ep.name}")
                elif issubclass(plugin_class, Extractor):
                    self._extractors[ep.name] = plugin_class
                    self._map_products(
                        ep.name,
                        plugin_class,
                        self._collection_to_extractors,
                        self._extractor_collection_mapping,
                    )
                    logger.debug(f"Loaded extractor: {ep.name}")
                else:
                    logger.warning(
                        f"Plugin '{ep.name}' does not inherit from SearchProvider or Extractor. Skipping."
                    )
            except Exception as e:
                logger.error(f"Failed to load plugin '{ep.name}': {e}")

    def _map_products(
        self,
        plugin_name: str,
        plugin_class: Type,
        target_map: Dict[str, List[str]],
        collection_mapping: Dict[str, Dict[str, str]],
    ) -> None:
        """Maps a plugin's supported_collections to the plugin name for fast lookups.

        Stores collection names in lowercase for case-insensitive matching,
        while also tracking original case for per-plugin name mapping.
        """
        # supported_collections is guaranteed to exist by the ABC __init_subclass__ hook
        plugin_canonical_map: Dict[str, str] = {}  # canonical -> original
        for product in plugin_class.supported_collections:
            # Store in lowercase for case-insensitive lookups
            lower_product = product.lower()
            target_map.setdefault(lower_product, []).append(plugin_name)
            # Track canonical-to-original mapping for this plugin
            plugin_canonical_map[lower_product] = product
            # Track first seen original case for display
            if lower_product not in self._original_collections:
                self._original_collections[lower_product] = product

        # Store per-plugin mapping
        collection_mapping[plugin_name] = plugin_canonical_map

    # --- Public API for the CLI / Orchestrator ---

    def list_supported_collections(self) -> List[str]:
        """Returns a list of all products supported by currently installed plugins.

        Returns collection names in their original case as defined by plugins.
        """
        # Combine keys from both maps and return unique values in original case
        all_products = set(self._collection_to_searchers.keys()).union(
            set(self._collection_to_extractors.keys())
        )
        # Map back to original case for display
        display_names = [self._original_collections.get(p, p) for p in all_products]
        return sorted(display_names)

    def find_searchers_for(self, collection_name: str) -> List[str]:
        """Returns names of search plugins that support the requested collection.

        Case-insensitive lookup. Wildcard plugins (supported_collections=["*"])
        are returned for any collection.
        """
        results = list(self._collection_to_searchers.get(collection_name.lower(), []))
        # Add wildcard plugins
        for plugin_name in self._collection_to_searchers.get("*", []):
            if plugin_name not in results:
                results.append(plugin_name)
        return results

    def find_extractors_for(self, collection_name: str) -> List[str]:
        """Returns names of extraction plugins that support the requested collection.

        Case-insensitive lookup. Wildcard plugins (supported_collections=["*"])
        are returned for any collection.
        """
        results = list(self._collection_to_extractors.get(collection_name.lower(), []))
        # Add wildcard plugins
        for plugin_name in self._collection_to_extractors.get("*", []):
            if plugin_name not in results:
                results.append(plugin_name)
        return results

    def get_searcher_collections(self, plugin_name: str) -> List[str]:
        if plugin_name in self._searchers:
            return list(self._searchers[plugin_name].supported_collections)
        return []

    def get_extractor_collections(self, plugin_name: str) -> List[str]:
        if plugin_name in self._extractors:
            return list(self._extractors[plugin_name].supported_collections)
        return []

    def has_searcher(self, plugin_name: str) -> bool:
        return plugin_name in self._searchers

    def has_extractor(self, plugin_name: str) -> bool:
        return plugin_name in self._extractors

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
        if plugin_name not in self._searcher_collection_mapping:
            return [c.lower() for c in collection_names]

        canonical_to_original = self._searcher_collection_mapping[plugin_name]
        # Wildcard plugins (e.g. ["*"]) should preserve user's original case
        if "*" in canonical_to_original:
            return list(collection_names)

        result = []
        for col in collection_names:
            canonical = col.lower()
            # Use plugin's original if known, otherwise fall back to lowercase
            mapped = canonical_to_original.get(canonical, canonical)
            result.append(mapped)
        return result

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
        if plugin_name not in self._extractor_collection_mapping:
            return [c.lower() for c in collection_names]

        canonical_to_original = self._extractor_collection_mapping[plugin_name]
        # Wildcard plugins (e.g. ["*"]) should preserve user's original case
        if "*" in canonical_to_original:
            return list(collection_names)

        result = []
        for col in collection_names:
            canonical = col.lower()
            # Use plugin's original if known, otherwise fall back to lowercase
            mapped = canonical_to_original.get(canonical, canonical)
            result.append(mapped)
        return result

    def get_searcher(self, plugin_name: str, **kwargs) -> SearchProvider:
        """Instantiates and returns a SearchProvider by name."""
        if plugin_name not in self._searchers:
            raise ValueError(
                f"Search plugin '{plugin_name}' not found or failed to load."
            )

        # Instantiate the plugin, passing any global configs (like API keys) via kwargs
        return self._searchers[plugin_name](**kwargs)

    def get_extractor(self, plugin_name: str, **kwargs) -> Extractor:
        """Instantiates and returns an Extractor by name."""
        if plugin_name not in self._extractors:
            raise ValueError(
                f"Extractor plugin '{plugin_name}' not found or failed to load."
            )

        return self._extractors[plugin_name](**kwargs)
