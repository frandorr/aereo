"""
Bootstrap component for initializing the aer plugin system
by loading all predefined plugin groups and registering them
with the plugin registry.
"""

from aer.bootstrap.core import bootstrap

__all__ = ["bootstrap"]
