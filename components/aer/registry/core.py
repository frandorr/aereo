import importlib.metadata
from typing import Dict, List, Type

# Importing the contracts we defined earlier
from aer.interfaces import Extractor, SearchProvider
from structlog import get_logger

logger = get_logger()


class AerRegistry:
    """
    Dynamically discovers and manages aer plugins via Python entry_points.
    """

    def __init__(self):
        # Store the class definitions, not instantiated objects
        self._searchers: Dict[str, Type[SearchProvider]] = {}
        self._extractors: Dict[str, Type[Extractor]] = {}

        # Fast-lookup maps: collection -> list of plugin names
        self._collection_to_searchers: Dict[str, List[str]] = {}
        self._collection_to_extractors: Dict[str, List[str]] = {}

        # Automatically load on instantiation
        self.discover_plugins()

    def discover_plugins(self) -> None:
        """Finds all installed packages declaring aer entry_points."""
        logger.info("Discovering aer plugins...")

        # 1. Load Search Providers
        searcher_eps = importlib.metadata.entry_points(group="aer.search_providers")
        for ep in searcher_eps:
            try:
                plugin_class = ep.load()
                if not issubclass(plugin_class, SearchProvider):
                    logger.warning(
                        f"Plugin '{ep.name}' does not inherit from SearchProvider. Skipping."
                    )
                    continue

                self._searchers[ep.name] = plugin_class
                self._map_products(ep.name, plugin_class, self._collection_to_searchers)
                logger.debug(f"Loaded searcher: {ep.name}")

            except Exception as e:
                logger.error(f"Failed to load searcher plugin '{ep.name}': {e}")

        # 2. Load Extractors
        extractor_eps = importlib.metadata.entry_points(group="aer.extractors")
        for ep in extractor_eps:
            try:
                plugin_class = ep.load()
                if not issubclass(plugin_class, Extractor):
                    logger.warning(
                        f"Plugin '{ep.name}' does not inherit from Extractor. Skipping."
                    )
                    continue

                self._extractors[ep.name] = plugin_class
                self._map_products(
                    ep.name, plugin_class, self._collection_to_extractors
                )
                logger.debug(f"Loaded extractor: {ep.name}")

            except Exception as e:
                logger.error(f"Failed to load extractor plugin '{ep.name}': {e}")

    def _map_products(
        self, plugin_name: str, plugin_class: Type, target_map: Dict[str, List[str]]
    ) -> None:
        """Maps a plugin's supported_collections to the plugin name for fast lookups."""
        # supported_collections is guaranteed to exist by the ABC __init_subclass__ hook
        for product in plugin_class.supported_collections:
            target_map.setdefault(product, []).append(plugin_name)

    # --- Public API for the CLI / Orchestrator ---

    def list_supported_collections(self) -> List[str]:
        """Returns a list of all products supported by currently installed plugins."""
        # Combine keys from both maps and return unique values
        all_products = set(self._collection_to_searchers.keys()).union(
            set(self._collection_to_extractors.keys())
        )
        return sorted(list(all_products))

    def find_searchers_for(self, collection_name: str) -> List[str]:
        """Returns names of search plugins that support the requested collection."""
        return self._collection_to_searchers.get(collection_name, [])

    def find_extractors_for(self, collection_name: str) -> List[str]:
        """Returns names of extraction plugins that support the requested collection."""
        return self._collection_to_extractors.get(collection_name, [])

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
