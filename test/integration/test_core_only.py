import pytest
from aer.search import SearchMethod


@pytest.fixture(autouse=True)
def reset_search_registry():
    """Reset the SearchMethod registry to avoid test pollution."""
    original_registry = SearchMethod._registry.copy()
    SearchMethod._registry.clear()
    SearchMethod._plugins_loaded = False
    yield
    SearchMethod._registry = original_registry
    SearchMethod._plugins_loaded = True


@pytest.mark.integration
def test_earthaccess_not_registered():
    """Verify that the earthaccess search plugin is NOT registered when only core is installed."""
    names = {m.name for m in SearchMethod.all()}
    assert "earthaccess" not in names
