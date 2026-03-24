import pytest
from aer.plugin import plugin_registry


@pytest.mark.integration
def test_dummy_search_registered():
    """Verify that the dummy-search plugin is correctly registered."""
    names = {m.name for m in plugin_registry.all()}
    assert "dummy-search" in names
