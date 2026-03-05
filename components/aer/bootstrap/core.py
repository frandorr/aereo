from aer.plugin import plugin_registry


def bootstrap() -> None:
    """Initialize the aer plugin system by loading all predefined groups."""
    plugin_registry.all()
