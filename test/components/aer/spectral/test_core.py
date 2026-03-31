"""Tests for the spectral component models.

Verifies channel type creation, immutability, Instrument and Satellite models,
and the create_channel factory for all schema types.
"""

import pytest

from aer.spectral import (
    BaseChannel,
    OpticalChannel,
    MicrowaveChannel,
    SARChannel,
    SpectrometerChannel,
    Instrument,
    Satellite,
    create_channel,
)


# ==========================================
#  Channel model tests
# ==========================================


def test_optical_channel_creation():
    """OpticalChannel can be created with required fields."""
    ch = OpticalChannel(
        channel_name="B1",
        instrument_acronym="VIIRS",
        central_wavelength=0.64,
        bandwidth=0.02,
        spatial_resolution=371.0,
    )
    assert ch.channel_name == "B1"
    assert ch.instrument_acronym == "VIIRS"
    assert ch.central_wavelength == 0.64
    assert ch.bandwidth == 0.02
    assert ch.spatial_resolution == 371.0
    assert ch.unit is None
    assert ch.snr_low is None


def test_optical_channel_with_optional_fields():
    """OpticalChannel accepts optional SNR fields."""
    ch = OpticalChannel(
        channel_name="B1",
        instrument_acronym="VIIRS",
        central_wavelength=0.64,
        bandwidth=0.02,
        spatial_resolution=371.0,
        unit="µm",
        snr_low=100.0,
        snr_high=200.0,
        snr_or_nedt="100",
    )
    assert ch.unit == "µm"
    assert ch.snr_low == 100.0
    assert ch.snr_high == 200.0
    assert ch.snr_or_nedt == "100"


def test_microwave_channel_creation():
    """MicrowaveChannel uses central_frequency instead of wavelength."""
    ch = MicrowaveChannel(
        channel_name="B1",
        instrument_acronym="AMSR2",
        central_frequency=6.925,
        bandwidth=0.35,
        spatial_resolution=62.0,
        polarisations="VH",
    )
    assert ch.central_frequency == 6.925
    assert ch.polarisations == "VH"


def test_sar_channel_creation():
    """SARChannel has operation_mode and resolution fields."""
    ch = SARChannel(
        channel_name="IW",
        instrument_acronym="SAR-C",
        operation_mode="IW",
        spatial_resolution=(5.0, 20.0),
        swath_width=250.0,
        polarisation="VV+VH",
    )
    assert ch.operation_mode == "IW"
    assert ch.spatial_resolution == (5.0, 20.0)
    assert ch.swath_width == 250.0


def test_sar_channel_single_resolution():
    """SARChannel accepts a single float for spatial_resolution."""
    ch = SARChannel(
        channel_name="SM",
        instrument_acronym="SAR-C",
        operation_mode="SM",
        spatial_resolution=5.0,
    )
    assert ch.spatial_resolution == 5.0


def test_spectrometer_channel_creation():
    """SpectrometerChannel uses wave numbers and spectral resolution."""
    ch = SpectrometerChannel(
        channel_name="Band1",
        instrument_acronym="IASI",
        wave_number_min=645.0,
        wave_number_max=2760.0,
        spectral_resolution=0.5,
        number_of_channels=8461,
    )
    assert ch.wave_number_min == 645.0
    assert ch.wave_number_max == 2760.0
    assert ch.spectral_resolution == 0.5


def test_all_channels_are_frozen():
    """All channel types are immutable (attrs.frozen)."""
    ch = OpticalChannel(
        channel_name="B1",
        instrument_acronym="VIIRS",
        central_wavelength=0.64,
        bandwidth=0.02,
        spatial_resolution=371.0,
    )
    with pytest.raises(AttributeError):
        ch.channel_name = "modified"  # type: ignore[misc]


def test_base_channel_is_frozen():
    """BaseChannel is immutable."""
    ch = BaseChannel(channel_name="B1", instrument_acronym="TEST")
    with pytest.raises(AttributeError):
        ch.channel_name = "modified"  # type: ignore[misc]


# ==========================================
#  create_channel factory tests
# ==========================================


def test_create_channel_optical():
    """create_channel builds OpticalChannel from dict data."""
    data = {
        "channel_name": "B1",
        "central_wavelength": 0.64,
        "bandwidth": 0.02,
        "spatial_resolution": 371.0,
    }
    ch = create_channel("optical_infrared", data, "VIIRS")
    assert isinstance(ch, OpticalChannel)
    assert ch.instrument_acronym == "VIIRS"
    assert ch.central_wavelength == 0.64


def test_create_channel_microwave():
    """create_channel builds MicrowaveChannel from dict data."""
    data = {
        "channel_name": "B1",
        "central_frequency": 6.925,
        "bandwidth": 0.35,
        "spatial_resolution": 62.0,
    }
    ch = create_channel("microwave", data, "AMSR2")
    assert isinstance(ch, MicrowaveChannel)
    assert ch.central_frequency == 6.925


def test_create_channel_sar():
    """create_channel builds SARChannel from dict data."""
    data = {
        "channel_name": "IW",
        "operation_mode": "IW",
        "spatial_resolution": 5.0,
        "swath_width": 250.0,
    }
    ch = create_channel("sar_active", data, "SAR-C")
    assert isinstance(ch, SARChannel)
    assert ch.operation_mode == "IW"


def test_create_channel_spectrometer():
    """create_channel builds SpectrometerChannel from dict data."""
    data = {
        "channel_name": "Band1",
        "wave_number_min": 645.0,
        "wave_number_max": 2760.0,
        "spectral_resolution": 0.5,
    }
    ch = create_channel("spectrometer_sounder", data, "IASI")
    assert isinstance(ch, SpectrometerChannel)
    assert ch.wave_number_min == 645.0


def test_create_channel_unknown_schema():
    """create_channel raises ValueError for unknown schema_type."""
    with pytest.raises(ValueError, match="Unknown schema_type"):
        create_channel("unknown", {}, "TEST")


def test_create_channel_float_str_conversion():
    """create_channel converts string numeric values to float for core fields."""
    data = {
        "channel_name": "B1",
        "central_wavelength": "0.64",
        "bandwidth": "0.02",
        "spatial_resolution": "371.0",
    }
    ch = create_channel("optical_infrared", data, "VIIRS")
    assert isinstance(ch, OpticalChannel)
    assert ch.central_wavelength == 0.64
    assert ch.bandwidth == 0.02
    assert ch.spatial_resolution == 371.0


def test_create_channel_snr_accepts_string():
    """SNR fields accept both float and string values."""
    data = {
        "channel_name": "B1",
        "central_wavelength": 0.64,
        "bandwidth": 0.02,
        "spatial_resolution": 371.0,
        "snr_low": "100",
    }
    ch = create_channel("optical_infrared", data, "VIIRS")
    assert isinstance(ch, OpticalChannel)
    assert ch.snr_low == "100"


# ==========================================
#  Instrument model tests
# ==========================================


def test_instrument_creation():
    """Instrument can be created with channels."""
    channels = [
        OpticalChannel(
            channel_name="B1",
            instrument_acronym="VIIRS",
            central_wavelength=0.64,
            bandwidth=0.02,
            spatial_resolution=371.0,
        ),
        OpticalChannel(
            channel_name="B2",
            instrument_acronym="VIIRS",
            central_wavelength=0.86,
            bandwidth=0.02,
            spatial_resolution=371.0,
        ),
    ]
    inst = Instrument(satellite_acronym="NPP", acronym="VIIRS", channels=channels)
    assert inst.acronym == "VIIRS"
    assert inst.satellite_acronym == "NPP"
    assert len(inst.channels) == 2


def test_instrument_repr():
    """Instrument repr includes acronym and channel count."""
    inst = Instrument(satellite_acronym="NPP", acronym="VIIRS", channels=[])
    repr_str = repr(inst)
    assert "VIIRS" in repr_str
    assert "Channels (0)" in repr_str


def test_instrument_is_frozen():
    """Instrument is immutable."""
    inst = Instrument(satellite_acronym="NPP", acronym="VIIRS", channels=[])
    with pytest.raises(AttributeError):
        inst.acronym = "modified"  # type: ignore[misc]


# ==========================================
#  Satellite model tests
# ==========================================


def test_satellite_creation():
    """Satellite can be created with payload instruments."""
    inst = Instrument(satellite_acronym="NPP", acronym="VIIRS", channels=[])
    sat = Satellite(
        acronym="NPP",
        payload=[inst],
        orbit="Sun-Synchronous",
        altitude_km=824.0,
        status="Operational",
        agencies=["NOAA", "NASA"],
    )
    assert sat.acronym == "NPP"
    assert len(sat.payload) == 1
    assert sat.orbit == "Sun-Synchronous"
    assert sat.altitude_km == 824.0
    assert sat.status == "Operational"
    assert sat.agencies == ["NOAA", "NASA"]


def test_satellite_with_optional_defaults():
    """Satellite can be created with minimal fields."""
    sat = Satellite(acronym="TEST", payload=[])
    assert sat.orbit is None
    assert sat.altitude_km is None
    assert sat.status is None
    assert sat.agencies is None


def test_satellite_repr():
    """Satellite repr includes acronym and payload info."""
    sat = Satellite(acronym="NPP", payload=[])
    repr_str = repr(sat)
    assert "NPP" in repr_str
    assert "Payload (0 instruments)" in repr_str


def test_satellite_is_frozen():
    """Satellite is immutable."""
    sat = Satellite(acronym="NPP", payload=[])
    with pytest.raises(AttributeError):
        sat.acronym = "modified"  # type: ignore[misc]
