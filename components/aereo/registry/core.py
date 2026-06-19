"""Plugin registry for aereo.

Discovers aereo plugins (search, read, reproject, process, write) via Python
entry points and exposes a uniform lookup API. See ``AereoRegistry`` for the
public entry point and ``PLUGIN_TYPES`` for the supported plugin kinds.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any, Sequence, Type

from aereo.interfaces.core import (
    BatchWriter,
    Processor,
    Reader,
    Reprojector,
    SearchProvider,
    Writer,
)
from structlog import get_logger

logger = get_logger()


def _get_supported_collections(plugin_class: Type) -> Sequence[str]:
    """Return the declared supported collections for a plugin class.

    Checks the class attribute first, then falls back to the Pydantic
    ``supported_collections`` field default.

    Args:
        plugin_class: Plugin class to inspect.

    Returns:
        Sequence of supported collection names, or an empty sequence.
    """
    supported = getattr(plugin_class, "supported_collections", None)
    if (
        supported is None
        and hasattr(plugin_class, "model_fields")
        and "supported_collections" in plugin_class.model_fields
    ):
        supported = plugin_class.model_fields["supported_collections"].default
    return supported or []


def _dump_params_pydantic(cls: Type, detailed: bool) -> dict[str, list[dict]]:
    """Derive parameter dictionary from Pydantic model fields.

    Args:
        cls: The plugin class (which inherits from Pydantic BaseModel).
        detailed: When ``True``, each param includes all details.

    Returns:
        A dict with "required" and "optional" parameter lists.
    """
    required = []
    optional = []

    for name, field in cls.model_fields.items():
        if name == "supported_collections":
            continue
        is_required = field.is_required()
        param_info = {
            "name": name,
            "default": field.default if not is_required else None,
            "type": str(field.annotation),
            "description": field.description or "",
        }
        if is_required:
            required.append(param_info)
        else:
            optional.append(param_info)

    return {"required": required, "optional": optional}


class _TypedRegistry:
    """Internal helper that manages plugins of a single type.

    Encapsulates the collections, mappings, and lookup logic so that
    ``AereoRegistry`` does not have to duplicate state for every plugin type.
    """

    def __init__(self) -> None:
        self.plugins: dict[str, Type] = {}
        self.collection_to_plugins: dict[str, list[str]] = {}
        self.collection_mapping: dict[str, dict[str, str]] = {}

    def register(
        self,
        plugin_name: str,
        plugin_class: Type,
        original_collections: dict[str, str],
    ) -> None:
        """Register a plugin and index its supported collections.

        Args:
            plugin_name: Entry-point name of the plugin.
            plugin_class: The plugin class to register.
            original_collections: Shared mapping of lowercase collection name to
                the first-seen original casing. Updated in-place.
        """
        self.plugins[plugin_name] = plugin_class

        plugin_canonical_map: dict[str, str] = {}
        supported = _get_supported_collections(plugin_class)
        for product in supported:
            lower_product = product.lower()
            self.collection_to_plugins.setdefault(lower_product, []).append(plugin_name)
            plugin_canonical_map[lower_product] = product
            if lower_product not in original_collections:
                original_collections[lower_product] = product

        self.collection_mapping[plugin_name] = plugin_canonical_map

    def find_for(self, collection_name: str, wildcard: str) -> list[str]:
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

    def get_collections(self, plugin_name: str) -> list[str]:
        """Return the supported collections for a plugin.

        Args:
            plugin_name: Entry-point name of the plugin.

        Returns:
            list of collection strings supported by the plugin, or an empty list
            if the plugin is not known.
        """
        if plugin_name in self.plugins:
            return list(_get_supported_collections(self.plugins[plugin_name]))
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
    ) -> list[str]:
        """Map user-provided collection names to the plugin's declared format.

        Args:
            plugin_name: Name of the plugin.
            collection_names: Collection names provided by user (any case).
            wildcard: The wildcard token (e.g. "*").

        Returns:
            list of collection names mapped to the plugin's declared format.
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
    ``PLUGIN_TYPES`` and one new base class.
    """

    ENTRY_POINT_GROUP: str = "aereo.plugins"
    WILDCARD: str = "*"

    # prefix -> (type_label, base_class)
    PLUGIN_TYPES: dict[str, tuple[str, Type]] = {
        "search_": ("searcher", SearchProvider),
        "read_": ("reader", Reader),
        "reproject_": ("reprojector", Reprojector),
        "process_": ("processor", Processor),
        "write_": ("writer", Writer),
        "batch_write_": ("batch_writer", BatchWriter),
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
        self._registries: dict[str, _TypedRegistry] = {
            label: _TypedRegistry() for label, _ in self.PLUGIN_TYPES.values()
        }

        # Expose the internal dicts directly so existing tests and consumers
        # that access ``_searchers`` continue to work.
        self._searchers: dict[str, Type[SearchProvider]] = self._registries[
            "searcher"
        ].plugins  # type: ignore[assignment]

        # Track original case for display in list_supported_collections
        self._original_collections: dict[str, str] = {}

        if auto_discover:
            self.discover_plugins()

    def _label_for(self, plugin_class: Type) -> str | None:
        """Return the registry label for a plugin class based on PLUGIN_TYPES."""
        for label, base_class in self.PLUGIN_TYPES.values():
            if issubclass(plugin_class, base_class):
                return label
        return None

    def register_plugins(self, plugins: dict[str, Type]) -> None:
        """Register pre-discovered plugins without scanning entry points.

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

    def find_for(self, type_label: str, collection_name: str) -> list[str]:
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

    def _try_lazy_load(self, plugin_name: str, type_label: str) -> bool:
        """Attempt to load a single plugin by name from entry points.

        Args:
            plugin_name: Entry-point name to look up.
            type_label: Expected plugin type label (e.g. "reader").

        Returns:
            True if the plugin was found, its type matches *type_label*, and
            it was registered. False otherwise.
        """
        try:
            eps = importlib.metadata.entry_points(group=self.ENTRY_POINT_GROUP)
            for ep in eps:
                if ep.name == plugin_name:
                    plugin_class = ep.load()
                    label = self._label_for(plugin_class)
                    if label is not None and label == type_label:
                        self._registries[label].register(
                            ep.name, plugin_class, self._original_collections
                        )
                        logger.debug(f"Lazy-loaded {label}: {ep.name}")
                        return True
                    elif label is not None:
                        logger.debug(
                            f"Plugin '{ep.name}' is a {label}, not {type_label}. Skipping."
                        )
                    else:
                        logger.warning(
                            f"Plugin '{ep.name}' does not inherit from any known base class."
                        )
                    break
        except Exception as e:
            logger.error(f"Failed to lazy-load plugin '{plugin_name}': {e}")
        return False

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
        if not registry.has(plugin_name):
            self._try_lazy_load(plugin_name, type_label)
        return registry.get(plugin_name, type_label.capitalize(), **kwargs)

    def has(self, type_label: str, plugin_name: str) -> bool:
        """Check whether a plugin of *type_label* with *plugin_name* is registered.

        Args:
            type_label: Plugin type label.
            plugin_name: Entry-point name of the plugin.

        Returns:
            True if registered (or successfully lazy-loaded), False otherwise.
        """
        registry = self._registries.get(type_label)
        if registry is None:
            return False
        if registry.has(plugin_name):
            return True
        return self._try_lazy_load(plugin_name, type_label)

    # --- Backward-compatible API ---

    def list_supported_collections(self) -> list[str]:
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

    def find_searchers_for(self, collection_name: str) -> list[str]:
        """Returns names of search plugins that support the requested collection."""
        return self._registries["searcher"].find_for(collection_name, self.WILDCARD)

    def get_searcher_collections(self, plugin_name: str) -> list[str]:
        """Return the supported collections for a named search plugin."""
        return self._registries["searcher"].get_collections(plugin_name)

    def has_searcher(self, plugin_name: str) -> bool:
        """Check whether a search plugin with the given name is registered."""
        return self.has("searcher", plugin_name)

    def get_collection_mapping_for_searcher(
        self, plugin_name: str, collection_names: Sequence[str]
    ) -> list[str]:
        """Maps user-provided collection names to a specific search plugin's declared format."""
        return self._registries["searcher"].get_collection_mapping(
            plugin_name, collection_names, self.WILDCARD
        )

    def get_searcher(self, plugin_name: str, **kwargs) -> SearchProvider:
        """Instantiates and returns a SearchProvider by name."""
        return self.get("searcher", plugin_name, **kwargs)

    def get_plugin_params(
        self, plugin_name: str, *, detailed: bool = True
    ) -> dict[str, list[dict]]:
        """Return params metadata for any plugin (search or pipeline stage).

        Args:
            plugin_name: Entry-point name of the plugin.
            detailed: When ``True`` (default), each param includes all
                attributes.

        Returns:
            {"required": [...], "optional": [...]} representing parameters.
        """
        cls: Type | None = None
        for registry in self._registries.values():
            cls = registry.plugins.get(plugin_name)
            if cls is not None:
                break

        if cls is None:
            raise KeyError(f"Unknown plugin: {plugin_name}")

        return _dump_params_pydantic(cls, detailed)

    def list_all_params(self, *, detailed: bool = True) -> dict[str, dict]:
        """JSON-serializable params catalog for all discovered plugins.

        Args:
            detailed: When ``True`` (default), each param includes all
                attributes.

        Returns:
            Mapping of plugin name to a dict with keys ``type``, ``required``,
            and ``optional``.
        """
        result: dict[str, dict] = {}
        for label, registry in self._registries.items():
            for name, cls in registry.plugins.items():
                params_dict = _dump_params_pydantic(cls, detailed)
                result[name] = {
                    "type": label,
                    "required": params_dict["required"],
                    "optional": params_dict["optional"],
                }
        return result
