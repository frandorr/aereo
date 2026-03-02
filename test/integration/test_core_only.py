from aer.search import SearchMethod


def test_earthaccess_not_registered():
    """Verify that the earthaccess search plugin is NOT registered when only core is installed."""
    names = {m.name for m in SearchMethod.all()}
    assert "earthaccess" not in names
