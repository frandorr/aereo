import pytest
from aer.search import SearchMethod


@pytest.mark.integration
def test_earthaccess_registered():
    """Verify that the earthaccess search plugin is correctly registered."""
    names = {m.name for m in SearchMethod.all()}
    assert "earthaccess" in names
