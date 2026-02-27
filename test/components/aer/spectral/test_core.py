from aer.spectral import (
    ABI_CHANNELS,
    VIIRS_CHANNELS,
    MODIS_CHANNELS,
    OLCI_CHANNELS,
    SLSTR_CHANNELS,
    Band,
    BandType,
    Channel,
    Instrument,
)


def test_abi_channel_count():
    assert len(ABI_CHANNELS) == 16


def test_viirs_channel_count():
    assert len(VIIRS_CHANNELS) == 22


def test_modis_channel_count():
    assert len(MODIS_CHANNELS) == 38


def test_olci_channel_count():
    assert len(OLCI_CHANNELS) == 21


def test_slstr_channel_count():
    assert len(SLSTR_CHANNELS) == 11


def test_channel_ids_unique_per_instrument():
    """Each instrument's channel tuple should have no duplicate c_id values."""
    instrument_channels = {
        "ABI": ABI_CHANNELS,
        "VIIRS": VIIRS_CHANNELS,
        "MODIS": MODIS_CHANNELS,
        "OLCI": OLCI_CHANNELS,
        "SLSTR": SLSTR_CHANNELS,
    }
    for name, channels in instrument_channels.items():
        ids = [ch.c_id for ch in channels]
        assert len(ids) == len(set(ids)), f"Duplicate channel IDs in {name}: {ids}"


def test_band_wavelengths_positive():
    """All channels should have positive wavelength, bandwidth, and resolution."""
    all_channels = (
        ABI_CHANNELS + VIIRS_CHANNELS + MODIS_CHANNELS + OLCI_CHANNELS + SLSTR_CHANNELS
    )
    for ch in all_channels:
        assert ch.band.central_wavelength > 0, f"{ch.c_id}: wavelength must be > 0"
        assert ch.band.bandwidth > 0, f"{ch.c_id}: bandwidth must be > 0"
        assert ch.resolution > 0, f"{ch.c_id}: resolution must be > 0"


def test_all_channels_are_frozen():
    """Channel and Band instances should be immutable (attrs.frozen)."""
    ch = ABI_CHANNELS[0]
    import pytest

    with pytest.raises(AttributeError):
        ch.c_id = "modified"
    with pytest.raises(AttributeError):
        ch.band.name = "modified"


def test_channel_instrument_consistency():
    """All channels in a tuple should belong to the same instrument."""
    for instrument, channels in [
        (Instrument.ABI, ABI_CHANNELS),
        (Instrument.VIIRS, VIIRS_CHANNELS),
        (Instrument.MODIS, MODIS_CHANNELS),
        (Instrument.OLCI, OLCI_CHANNELS),
        (Instrument.SLSTR, SLSTR_CHANNELS),
    ]:
        for ch in channels:
            assert ch.instrument == instrument, (
                f"Channel {ch.c_id} has instrument {ch.instrument}, expected {instrument}"
            )


def test_band_type_values():
    """All band_type values should be valid BandType enum members."""
    all_channels = (
        ABI_CHANNELS + VIIRS_CHANNELS + MODIS_CHANNELS + OLCI_CHANNELS + SLSTR_CHANNELS
    )
    for ch in all_channels:
        assert isinstance(ch.band.band_type, BandType), (
            f"Channel {ch.c_id}: band_type {ch.band.band_type} is not a BandType"
        )


def test_channel_equality():
    """Channels with the same attributes should be equal (attrs structural equality)."""
    ch1 = Channel(
        c_id="test",
        instrument=Instrument.ABI,
        band=Band(
            name="Test",
            band_type=BandType.VISIBLE,
            central_wavelength=0.5,
            bandwidth=0.01,
        ),
        resolution=1000,
    )
    ch2 = Channel(
        c_id="test",
        instrument=Instrument.ABI,
        band=Band(
            name="Test",
            band_type=BandType.VISIBLE,
            central_wavelength=0.5,
            bandwidth=0.01,
        ),
        resolution=1000,
    )
    assert ch1 == ch2


def test_shortwave_infrared_category_exists():
    """Verify that SHORTWAVE_INFRARED bands exist where expected."""
    swir_abi = [
        ch for ch in ABI_CHANNELS if ch.band.band_type == BandType.SHORTWAVE_INFRARED
    ]
    assert len(swir_abi) == 3  # bands 4, 5, 6

    swir_viirs = [
        ch for ch in VIIRS_CHANNELS if ch.band.band_type == BandType.SHORTWAVE_INFRARED
    ]
    assert len(swir_viirs) == 5  # M8, M9, M10, M11, I3

    swir_modis = [
        ch for ch in MODIS_CHANNELS if ch.band.band_type == BandType.SHORTWAVE_INFRARED
    ]
    assert len(swir_modis) == 2  # bands 6, 7

    swir_slstr = [
        ch for ch in SLSTR_CHANNELS if ch.band.band_type == BandType.SHORTWAVE_INFRARED
    ]
    assert len(swir_slstr) == 2  # S5, S6
