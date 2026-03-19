from typing import Any

import pytest

from aer.plugin import plugin, run_extract, run_search


@plugin(name="mock-search", category="search")
def _mock_search(query: Any, **kwargs: Any) -> dict[str, Any]:
    """A mock search plugin for testing."""
    return {"query": query, "kwargs": kwargs, "result": "search_ok"}


@plugin(name="mock-extract", category="extract")
def _mock_extract(gdf: Any, output_dir: str, **kwargs: Any) -> dict[str, Any]:
    """A mock extract plugin for testing."""
    return {
        "gdf": gdf,
        "output_dir": output_dir,
        "kwargs": kwargs,
        "result": "extract_ok",
    }


def test_run_search() -> None:
    """run_search dispatches to the correct search plugin."""
    result = run_search("mock-search", "test_query", extra="val")
    assert result["query"] == "test_query"
    assert result["kwargs"] == {"extra": "val"}
    assert result["result"] == "search_ok"


def test_run_extract() -> None:
    """run_extract dispatches to the correct extract plugin."""
    result = run_extract("mock-extract", "test_gdf", "/tmp/out", extra="val")
    assert result["gdf"] == "test_gdf"
    assert result["output_dir"] == "/tmp/out"
    assert result["kwargs"] == {"extra": "val"}
    assert result["result"] == "extract_ok"


def test_run_search_not_found() -> None:
    """run_search raises KeyError when plugin not registered."""
    with pytest.raises(KeyError, match="nonexistent"):
        run_search("nonexistent", "query")


def test_run_extract_not_found() -> None:
    """run_extract raises KeyError when plugin not registered."""
    with pytest.raises(KeyError, match="nonexistent"):
        run_extract("nonexistent", "gdf", "/tmp/out")
