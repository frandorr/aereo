import pytest
from aer.plugin import plugin_registry


@pytest.mark.integration
def test_earthaccess_registered():
    """Verify that the earthaccess plugin is correctly registered."""
    names = {m.name for m in plugin_registry.all()}
    assert "search_earthaccess" in names
