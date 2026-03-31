"""Test demonstrating how a 3rd party plugin registers instruments and products.

Shows creating Instruments with channels using the create_channel factory
and Satellite models with payload instruments.
"""

from aer.spectral import (
    Instrument,
    Satellite,
    OpticalChannel,
    MicrowaveChannel,
    create_channel,
)


def test_instrument_with_multiple_channel_types():
    """Instruments can hold channels of different types."""
    channels = [
        OpticalChannel(
            channel_name="B1",
            instrument_acronym="OLI",
            central_wavelength=0.443,
            bandwidth=0.016,
            spatial_resolution=30.0,
        ),
        OpticalChannel(
            channel_name="B2",
            instrument_acronym="OLI",
            central_wavelength=0.482,
            bandwidth=0.060,
            spatial_resolution=30.0,
        ),
    ]
    inst = Instrument(satellite_acronym="LANDSAT_8", acronym="OLI", channels=channels)
    assert inst.acronym == "OLI"
    assert len(inst.channels) == 2
    assert all(isinstance(ch, OpticalChannel) for ch in inst.channels)


def test_create_channel_factory_integration():
    """create_channel factory produces channels that work with Instrument."""
    data = {
        "channel_name": "B1",
        "central_wavelength": 0.443,
        "bandwidth": 0.016,
        "spatial_resolution": 30.0,
    }
    ch = create_channel("optical_infrared", data, "OLI")
    assert isinstance(ch, OpticalChannel)

    inst = Instrument(satellite_acronym="LANDSAT_8", acronym="OLI", channels=[ch])
    assert inst.channels[0].channel_name == "B1"
    assert isinstance(inst.channels[0], OpticalChannel)
    assert inst.channels[0].central_wavelength == 0.443


def test_satellite_with_multiple_instruments():
    """Satellites can carry multiple instruments."""
    inst1 = Instrument(
        satellite_acronym="LANDSAT_8",
        acronym="OLI",
        channels=[
            OpticalChannel(
                channel_name="B1",
                instrument_acronym="OLI",
                central_wavelength=0.443,
                bandwidth=0.016,
                spatial_resolution=30.0,
            )
        ],
    )
    inst2 = Instrument(
        satellite_acronym="LANDSAT_8",
        acronym="TIRS",
        channels=[
            OpticalChannel(
                channel_name="B10",
                instrument_acronym="TIRS",
                central_wavelength=10.9,
                bandwidth=0.8,
                spatial_resolution=100.0,
            )
        ],
    )
    sat = Satellite(acronym="LANDSAT_8", payload=[inst1, inst2])
    assert len(sat.payload) == 2
    assert sat.payload[0].acronym == "OLI"
    assert sat.payload[1].acronym == "TIRS"


def test_mixed_channel_types_in_instrument():
    """An instrument can have mixed channel types."""
    channels = [
        OpticalChannel(
            channel_name="VIS",
            instrument_acronym="MIXED",
            central_wavelength=0.65,
            bandwidth=0.05,
            spatial_resolution=500.0,
        ),
        MicrowaveChannel(
            channel_name="MW1",
            instrument_acronym="MIXED",
            central_frequency=89.0,
            bandwidth=3.0,
            spatial_resolution=5.0,
        ),
    ]
    inst = Instrument(satellite_acronym="TEST", acronym="MIXED", channels=channels)
    assert isinstance(inst.channels[0], OpticalChannel)
    assert isinstance(inst.channels[1], MicrowaveChannel)
