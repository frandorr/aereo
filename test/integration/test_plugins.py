from aer.search import SearchMethod


def test_earthaccess_registered():
    """Verify that the earthaccess search plugin is correctly registered."""
    names = {m.name for m in SearchMethod.all()}
    assert "earthaccess" in names
