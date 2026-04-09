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
        # REQUIRED: declare plugin type and products
        plugin_type = "search"
        supported_products = ["goes-16", "modis"]

        @hookimpl
        def search(self, collections, intersects, time_range, search_params):
            # Your search logic here
            return my_api.search(collections, intersects, time_range, search_params)

2. Register via entry point in ``pyproject.toml``::

    [project.entry-points."aer.plugins"]
    my_plugin = "my_package.module:MySearchPlugin"

3. Users interact with the simple pipeline API::

    from aer.plugin.api import run_search, create_tasks, run_extract

    # Search for data
    results = run_search(products=["goes-16"])

    # Create extraction tasks
    tasks = create_tasks(results, intersects=my_geom, output_path="/tmp")

    # Extract data
    for task in tasks:
        run_extract(task, plugin_name="my_plugin")

Available Hooks
---------------

- **search**: Query satellite data collections
- **prepare_tasks**: Transform search results into extraction tasks
- **extract**: Download and reproject data to the standard grid

See ``AerSpec`` class for full documentation of each hook.
"""

from aer.plugin.core import (
    AerSpec,
    PLUGIN_TYPE_ATTR,
    Product,
    SUPPORTED_PRODUCTS_ATTR,
    get_plugin_type,
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

from aer.plugin.api import (
    create_tasks,
    list_available_products,
    list_plugins,
    run_extract,
    run_search,
)

__all__ = [
    "AerSpec",
    "PLUGIN_TYPE_ATTR",
    "Product",
    "SUPPORTED_PRODUCTS_ATTR",
    "get_plugin_type",
    "get_supported_products",
    "hookimpl",
    "hookspec",
    "PROJECT_NAME",
    "SearchResultSchema",
    "NoMatchingPluginError",
    "PluginConflictError",
    "PluginSelector",
    "create_tasks",
    "list_available_products",
    "list_plugins",
    "run_extract",
    "run_search",
]
