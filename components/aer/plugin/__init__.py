"""
Plugin system for extending aer with custom search and extract capabilities.

External packages implement AerSpec hooks using ``@hookimpl`` to provide
custom satellite data search and extraction operations.

Quick Start for Plugin Developers
---------------------------------

1. Create a plugin class implementing one or more hooks::

    from aer.plugin import hookimpl, AerSpec
    from pandera.typing.geopandas import GeoDataFrame
    from aer.search import SearchQuery

    class MySearchPlugin:
        @hookimpl
        def search(self, query: SearchQuery) -> GeoDataFrame:
            # Your search logic here
            return my_api.search(query)

2. Register via entry point in ``pyproject.toml``::

    [project.entry-points."aer.plugins"]
    my_plugin = "my_package.module:MySearchPlugin"

3. Users can now use your plugin::

    import pluggy
    from aer.plugin import AerSpec, PROJECT_NAME

    pm = pluggy.PluginManager(PROJECT_NAME)
    pm.add_hookspecs(AerSpec)
    pm.load_setuptools_entrypoints("aer.plugins")

    # Your plugin is automatically available via the hook system
    results = pm.hook.search(query=my_query)

Available Hooks
---------------

- **search**: Query satellite data collections
- **prepare_tasks**: Transform search results into extraction tasks
- **extract**: Download and reproject data to the standard grid

See ``AerSpec`` class for full documentation of each hook.
"""

from aer.plugin.core import (
    AerSpec,
    Product,
    SUPPORTED_PRODUCTS_ATTR,
    get_supported_products,
    hookimpl,
    hookspec,
    PROJECT_NAME,
    SearchResultSchema,
)

from aer.plugin.selector import (
    NoMatchingPluginError,
    PluginConflictError,
    PluginSelector,
)

__all__ = [
    "AerSpec",
    "Product",
    "SUPPORTED_PRODUCTS_ATTR",
    "get_supported_products",
    "hookimpl",
    "hookspec",
    "PROJECT_NAME",
    "SearchResultSchema",
    "NoMatchingPluginError",
    "PluginConflictError",
    "PluginSelector",
]
