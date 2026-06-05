"""Tests for build_collection_asset_filters utility."""

from __future__ import annotations

from aereo.interfaces import build_collection_asset_filters


class TestBuildCollectionAssetFilters:
    """Tests for build_collection_asset_filters."""

    def test_empty_profiles(self) -> None:
        """No config yields empty results."""
        cols, filters = build_collection_asset_filters(None)
        assert cols == []
        assert filters == {}

    def test_single_profile_with_specific_assets(self) -> None:
        """A mapping with specific asset keys returns those keys."""
        cols, filters = build_collection_asset_filters({"s2": ["B02", "B03", "B04"]})
        assert cols == ["s2"]
        assert filters["s2"] == {"B02", "B03", "B04"}

    def test_single_profile_wildcard(self) -> None:
        """Wildcard '*' in vars list maps to None (all assets)."""
        cols, filters = build_collection_asset_filters({"s2": ["*"]})
        assert cols == ["s2"]
        assert filters["s2"] is None

    def test_single_profile_empty_vars(self) -> None:
        """Empty vars list means all assets (None)."""
        cols, filters = build_collection_asset_filters({"s2": []})
        assert cols == ["s2"]
        assert filters["s2"] is None

    def test_multiple_collections(self) -> None:
        """Config spanning different collections yields all of them."""
        cols, filters = build_collection_asset_filters(
            {"s2": ["B02", "B08"], "landsat": ["B4"]}
        )
        assert set(cols) == {"s2", "landsat"}
        assert filters["s2"] == {"B02", "B08"}
        assert filters["landsat"] == {"B4"}

    def test_collection_order_preserved(self) -> None:
        """Collections appear in insertion order."""
        cols, _ = build_collection_asset_filters({"alpha": ["x", "z"], "beta": ["y"]})
        assert cols == ["alpha", "beta"]
