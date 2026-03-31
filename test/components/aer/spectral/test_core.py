"""Tests for the spectral component models.

Verifies instrument channel counts, channel uniqueness, band wavelength validity,
immutability, instrument consistency, and BandType enum values.
"""

from aer.spectral import (  # type: ignore[attr-defined]
    Band,
    BandType,
    Channel,
    Instrument,
    Product,
)


def get_instrument_channels(instrument_name: str) -> tuple[Channel, ...]:
    # We can reconstruct all channels of an instrument from the products, or
    # collect all unique channels because product channels refer to them.
    # Alternatively, since we don't have a global Channel registry,
    # let's aggregate them from the registered Products.
    channels = set()
    for product in Product.all():
        if product.instrument.name == instrument_name:
            for ch in product.channels:
                channels.add(ch)

    # Sort them by ID conceptually to make tests deterministic if needed
    return tuple(channels)


def test_abi_channel_count():
    assert len(get_instrument_channels("ABI")) == 16


def test_viirs_channel_count():
    assert len(get_instrument_channels("VIIRS")) == 22


def test_modis_channel_count():
    assert len(get_instrument_channels("MODIS")) == 38


def test_olci_channel_count():
    assert len(get_instrument_channels("OLCI")) == 21


def test_slstr_channel_count():
    assert len(get_instrument_channels("SLSTR")) == 11


def test_channel_ids_unique_per_instrument():
    """Each instrument's channel tuple should have no duplicate c_id values."""
    for name in ["ABI", "VIIRS", "MODIS", "OLCI", "SLSTR"]:
        channels = get_instrument_channels(name)
        ids = [ch.c_id for ch in channels]
        assert len(ids) == len(set(ids)), f"Duplicate channel IDs in {name}: {ids}"


def test_band_wavelengths_positive():
    """All channels should have positive wavelength, bandwidth, and resolution."""
    all_channels = set()
    for product in Product.all():
        for ch in product.channels:
            all_channels.add(ch)

    for ch in all_channels:
        assert ch.band.central_wavelength > 0, f"{ch.c_id}: wavelength must be > 0"
        assert ch.band.bandwidth > 0, f"{ch.c_id}: bandwidth must be > 0"
        assert ch.resolution > 0, f"{ch.c_id}: resolution must be > 0"


def test_all_channels_are_frozen():
    """Channel and Band instances should be immutable (attrs.frozen)."""
    ch = get_instrument_channels("ABI")[0]
    import pytest

    with pytest.raises(AttributeError):
        ch.c_id = "modified"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        ch.band.name = "modified"  # type: ignore[misc]


def test_channel_instrument_consistency():
    """All channels in a tuple should belong to the same instrument."""
    for instrument_name in ["ABI", "VIIRS", "MODIS", "OLCI", "SLSTR"]:
        channels = get_instrument_channels(instrument_name)
        instrument = Instrument.get(instrument_name)
        for ch in channels:
            assert ch.instrument == instrument, (
                f"Channel {ch.c_id} has instrument {ch.instrument}, expected {instrument}"
            )


def test_band_type_values():
    """All band_type values should be valid BandType instances."""
    all_channels = set()
    for product in Product.all():
        for ch in product.channels:
            all_channels.add(ch)

    for ch in all_channels:
        assert isinstance(ch.band.band_type, BandType), (
            f"Channel {ch.c_id}: band_type {ch.band.band_type} is not a BandType"
        )


def test_channel_equality():
    """Channels with the same attributes should be equal (attrs structural equality)."""
    ch1 = Channel(
        c_id="test",
        instrument=Instrument.get("ABI"),
        band=Band(
            name="Test",
            band_type=BandType.get("Visible"),
            central_wavelength=0.5,
            bandwidth=0.01,
        ),
        resolution=1000,
    )
    ch2 = Channel(
        c_id="test",
        instrument=Instrument.get("ABI"),
        band=Band(
            name="Test",
            band_type=BandType.get("Visible"),
            central_wavelength=0.5,
            bandwidth=0.01,
        ),
        resolution=1000,
    )
    assert ch1 == ch2


def test_shortwave_infrared_category_exists():
    """Verify that SHORTWAVE_INFRARED bands exist where expected."""
    swir_abi = [
        ch
        for ch in get_instrument_channels("ABI")
        if ch.band.band_type.name == "Shortwave Infrared"
    ]
    assert len(swir_abi) == 3  # bands 4, 5, 6

    swir_viirs = [
        ch
        for ch in get_instrument_channels("VIIRS")
        if ch.band.band_type.name == "Shortwave Infrared"
    ]
    assert len(swir_viirs) == 5  # M8, M9, M10, M11, I3

    swir_modis = [
        ch
        for ch in get_instrument_channels("MODIS")
        if ch.band.band_type.name == "Shortwave Infrared"
    ]
    assert len(swir_modis) == 2  # bands 6, 7

    swir_slstr = [
        ch
        for ch in get_instrument_channels("SLSTR")
        if ch.band.band_type.name == "Shortwave Infrared"
    ]
    assert len(swir_slstr) == 2  # S5, S6
