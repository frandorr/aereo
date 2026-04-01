"""Tests for the catalog component core models."""

import pytest
from aer.catalog.core import Asset, AssetVariable, Product
from aer.spectral import Instrument, Satellite
from shapely.geometry import Polygon


@pytest.fixture
def sample_instrument():
    return Instrument(
        acronym="ABI",
        channels=[],
    )


@pytest.fixture
def sample_satellite(sample_instrument):
    return Satellite(
        acronym="GOES-16",
        payload=[sample_instrument],
    )


@pytest.fixture
def sample_product(sample_instrument, sample_satellite):
    return Product(
        product_id="ABI-L1b-RadF",
        processing_level="L1b",
        instruments=[sample_instrument],
        satellites=[sample_satellite],
        metadata={"description": "Full disk radiance product"},
    )


@pytest.fixture
def sample_polygon():
    return Polygon([(-180, -80), (-180, 84), (180, 84), (180, -80)])


class TestProduct:
    """Tests for Product model."""

    def test_product_creation(self, sample_instrument, sample_satellite):
        """Product can be created with required fields."""
        product = Product(
            product_id="test-product",
            processing_level="L1",
            instruments=[sample_instrument],
            satellites=[sample_satellite],
        )
        assert product.product_id == "test-product"
        assert product.processing_level == "L1"
        assert len(product.instruments) == 1
        assert len(product.satellites) == 1

    def test_product_default_metadata(self, sample_instrument, sample_satellite):
        """Product has empty dict as default metadata."""
        product = Product(
            product_id="test-product",
            processing_level="L1",
            instruments=[sample_instrument],
            satellites=[sample_satellite],
        )
        assert product.metadata == {}

    def test_product_with_metadata(self, sample_instrument, sample_satellite):
        """Product accepts custom metadata."""
        metadata = {"key": "value", "count": 42}
        product = Product(
            product_id="test-product",
            processing_level="L1",
            instruments=[sample_instrument],
            satellites=[sample_satellite],
            metadata=metadata,
        )
        assert product.metadata == metadata

    def test_product_is_immutable(self, sample_instrument, sample_satellite):
        """Product is frozen and cannot be modified."""
        product = Product(
            product_id="test-product",
            processing_level="L1",
            instruments=[sample_instrument],
            satellites=[sample_satellite],
        )
        # Direct assignment to frozen attrs class raises FrozenAttributeError
        with pytest.raises(Exception):
            product.product_id = "new-id"  # pyright: ignore[reportAttributeAccessIssue]

    def test_product_multiple_instruments_and_satellites(
        self, sample_instrument, sample_satellite
    ):
        """Product can have multiple instruments and satellites."""
        instrument2 = Instrument(
            acronym="ABI",
            channels=[],
        )
        satellite2 = Satellite(
            acronym="GOES-18",
            payload=[instrument2],
        )
        product = Product(
            product_id="multi-product",
            processing_level="L2",
            instruments=[sample_instrument, instrument2],
            satellites=[sample_satellite, satellite2],
        )
        assert len(product.instruments) == 2
        assert len(product.satellites) == 2


class TestAssetVariable:
    """Tests for AssetVariable model."""

    def test_asset_variable_creation(self):
        """AssetVariable can be created with required fields."""
        var = AssetVariable(name="CMI", role="channel")
        assert var.name == "CMI"
        assert var.role == "channel"
        assert var.metadata == {}

    def test_asset_variable_default_metadata(self):
        """AssetVariable has empty dict as default metadata."""
        var = AssetVariable(name="Mask", role="mask")
        assert var.metadata == {}

    def test_asset_variable_with_metadata(self):
        """AssetVariable accepts custom metadata."""
        metadata = {"flag_meanings": {0: "water", 1: "fire", 2: "cloud"}}
        var = AssetVariable(name="Mask", role="mask", metadata=metadata)
        assert var.metadata == metadata

    def test_asset_variable_is_immutable(self):
        """AssetVariable is frozen and cannot be modified."""
        var = AssetVariable(name="CMI", role="channel")
        # Direct assignment to frozen attrs class raises FrozenAttributeError
        with pytest.raises(Exception):
            var.name = "new-name"  # pyright: ignore[reportAttributeAccessIssue]

    def test_asset_variable_various_roles(self):
        """AssetVariable supports different role types."""
        roles = ["channel", "mask", "geolocation", "quality_flag", "generic"]
        for role in roles:
            var = AssetVariable(name=f"var_{role}", role=role)
            assert var.role == role


class TestAsset:
    """Tests for Asset model."""

    def test_asset_creation(self, sample_product, sample_polygon):
        """Asset can be created with required fields."""
        asset = Asset(
            product=sample_product,
            url="https://example.com/data.nc",
            spatial_coverage=sample_polygon,
        )
        assert asset.product is sample_product
        assert asset.url == "https://example.com/data.nc"
        assert asset.spatial_coverage == sample_polygon
        assert asset.variables == []
        assert asset.metadata == {}

    def test_asset_default_variables(self, sample_product, sample_polygon):
        """Asset has empty list as default variables."""
        asset = Asset(
            product=sample_product,
            url="https://example.com/data.nc",
            spatial_coverage=sample_polygon,
        )
        assert asset.variables == []

    def test_asset_default_metadata(self, sample_product, sample_polygon):
        """Asset has empty dict as default metadata."""
        asset = Asset(
            product=sample_product,
            url="https://example.com/data.nc",
            spatial_coverage=sample_polygon,
        )
        assert asset.metadata == {}

    def test_asset_with_variables(self, sample_product, sample_polygon):
        """Asset accepts variables list."""
        variables = [
            AssetVariable(name="CMI", role="channel"),
            AssetVariable(name="Mask", role="mask"),
        ]
        asset = Asset(
            product=sample_product,
            url="https://example.com/data.nc",
            spatial_coverage=sample_polygon,
            variables=variables,
        )
        assert len(asset.variables) == 2
        assert asset.variables[0].name == "CMI"
        assert asset.variables[1].name == "Mask"

    def test_asset_with_metadata(self, sample_product, sample_polygon):
        """Asset accepts custom metadata."""
        metadata = {"cloud_hosted": True, "region": "us-east-1"}
        asset = Asset(
            product=sample_product,
            url="https://example.com/data.nc",
            spatial_coverage=sample_polygon,
            metadata=metadata,
        )
        assert asset.metadata == metadata

    def test_asset_is_immutable(self, sample_product, sample_polygon):
        """Asset is frozen and cannot be modified."""
        asset = Asset(
            product=sample_product,
            url="https://example.com/data.nc",
            spatial_coverage=sample_polygon,
        )
        # Direct assignment to frozen attrs class raises FrozenAttributeError
        with pytest.raises(Exception):
            asset.url = "https://new-url.com"  # pyright: ignore[reportAttributeAccessIssue]

    def test_asset_spatial_coverage_is_polygon(self, sample_product, sample_polygon):
        """Asset spatial_coverage is a Polygon."""
        asset = Asset(
            product=sample_product,
            url="https://example.com/data.nc",
            spatial_coverage=sample_polygon,
        )
        assert asset.spatial_coverage.geom_type == "Polygon"

    def test_asset_with_different_polygons(self, sample_product):
        """Asset accepts various polygon shapes."""
        small_polygon = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
        large_polygon = Polygon([(-180, -90), (-180, 90), (180, 90), (180, -90)])

        asset_small = Asset(
            product=sample_product,
            url="https://example.com/small.nc",
            spatial_coverage=small_polygon,
        )
        asset_large = Asset(
            product=sample_product,
            url="https://example.com/large.nc",
            spatial_coverage=large_polygon,
        )

        assert asset_small.spatial_coverage != asset_large.spatial_coverage


class TestCatalogIntegration:
    """Integration tests for catalog component relationships."""

    def test_product_asset_variable_relationship(self, sample_product, sample_polygon):
        """Asset links Product with AssetVariables."""
        variables = [
            AssetVariable(name="CMI", role="channel"),
            AssetVariable(name="latitude", role="geolocation"),
        ]
        asset = Asset(
            product=sample_product,
            url="https://example.com/data.nc",
            spatial_coverage=sample_polygon,
            variables=variables,
        )

        assert asset.product.product_id == "ABI-L1b-RadF"
        assert len(asset.variables) == 2
        assert asset.variables[0].role == "channel"
        assert asset.variables[1].role == "geolocation"

    def test_asset_inherits_product_instruments(self, sample_product, sample_polygon):
        """Asset can access instrument information through product."""
        asset = Asset(
            product=sample_product,
            url="https://example.com/data.nc",
            spatial_coverage=sample_polygon,
        )

        assert len(asset.product.instruments) == 1
        assert asset.product.instruments[0].acronym == "ABI"

    def test_asset_inherits_product_satellites(self, sample_product, sample_polygon):
        """Asset can access satellite information through product."""
        asset = Asset(
            product=sample_product,
            url="https://example.com/data.nc",
            spatial_coverage=sample_polygon,
        )

        assert len(asset.product.satellites) == 1
        assert asset.product.satellites[0].acronym == "GOES-16"
