from aer.plugins import load_multiple_groups

PLUGIN_GROUPS = [
    "aer.plugins.search",
    "aer.plugins.ingest",
    "aer.plugins.export",
]


def bootstrap() -> None:
    """Initialize the aer plugin system by loading all predefined groups."""
    load_multiple_groups(PLUGIN_GROUPS)
