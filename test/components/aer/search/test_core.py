import pytest
from datetime import datetime
import pandas as pd

from aer.search import SearchMethod
from aer.temporal import TimeRange
from aer.spectral import VNP02IMG


def test_searchmethod_registry():
    """Test the SearchMethod registry and basic plugin behavior."""

    # Create a dummy search function
    def dummy_search(
        products,
        time_range,
        spatial_extent=None,
        cell_overlap_mode="contains",
        **kwargs,
    ):
        return pd.DataFrame([{"product_name": products[0].name, "dummy_flag": True}])

    # 1. Register a new plugin
    dummy_plugin = SearchMethod.register("dummy_plugin", dummy_search)
    assert dummy_plugin.name == "dummy_plugin"

    # 2. Retrieve plugin
    retrieved = SearchMethod.get("dummy_plugin")
    assert retrieved is dummy_plugin

    # 3. Double registering the exact same function returns the existing instance
    dummy_plugin_2 = SearchMethod.register("dummy_plugin", dummy_search)
    assert dummy_plugin_2 is dummy_plugin

    # 4. Registering a different function with the same name raises ValueError
    def dummy_search_other(*args, **kwargs):
        pass

    with pytest.raises(
        ValueError, match="already registered with a different function"
    ):
        SearchMethod.register("dummy_plugin", dummy_search_other)

    # 4. Check 'all' contains our new plugin
    all_plugins = SearchMethod.all()
    assert dummy_plugin in all_plugins

    # 5. Check 'all' contains pre-registered plugins
    earthaccess_plugin = SearchMethod.get("earthaccess")
    assert earthaccess_plugin in all_plugins

    # 6. Verify missing plugin raises KeyError
    with pytest.raises(KeyError, match="not registered"):
        SearchMethod.get("non_existent_plugin")

    # 7. Execution through the SearchMethod class (calls __call__)
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )
    df = dummy_plugin(products=[VNP02IMG], time_range=time_range)
    assert not df.empty
    assert df.iloc[0]["product_name"] == VNP02IMG.name
    assert bool(df.iloc[0]["dummy_flag"])
