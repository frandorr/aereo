from aer.spectral import Band, BandType, Channel, Instrument, Satellite

# Register VIIRS sats and instrument
Instrument.register("VIIRS", "https://space.oscar.wmo.int/instruments/view/viirs")
Satellite.register("NOAA-20", "https://space.oscar.wmo.int/satellites/view/noaa-20")
Satellite.register("NOAA-21", "https://space.oscar.wmo.int/satellites/view/noaa-21")
Satellite.register("SNPP", "https://space.oscar.wmo.int/satellites/view/snpp")

VIIRS_CONSTELLATION = frozenset(
    [Satellite.get("SNPP"), Satellite.get("NOAA-20"), Satellite.get("NOAA-21")]
)

VIIRS_M1 = Channel(
    c_id="M1",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M1",
        band_type=BandType.get("Visible"),
        central_wavelength=0.412,
        bandwidth=0.020,
    ),
    resolution=750,
)
VIIRS_M2 = Channel(
    c_id="M2",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M2",
        band_type=BandType.get("Visible"),
        central_wavelength=0.445,
        bandwidth=0.018,
    ),
    resolution=750,
)
VIIRS_M3 = Channel(
    c_id="M3",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M3",
        band_type=BandType.get("Visible"),
        central_wavelength=0.488,
        bandwidth=0.020,
    ),
    resolution=750,
)
VIIRS_M4 = Channel(
    c_id="M4",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M4",
        band_type=BandType.get("Visible"),
        central_wavelength=0.555,
        bandwidth=0.020,
    ),
    resolution=750,
)
VIIRS_M5 = Channel(
    c_id="M5",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M5",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.672,
        bandwidth=0.020,
    ),
    resolution=750,
)
VIIRS_M6 = Channel(
    c_id="M6",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M6",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.746,
        bandwidth=0.015,
    ),
    resolution=750,
)
VIIRS_M7 = Channel(
    c_id="M7",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M7",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.865,
        bandwidth=0.039,
    ),
    resolution=750,
)
VIIRS_M8 = Channel(
    c_id="M8",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M8",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=1.240,
        bandwidth=0.020,
    ),
    resolution=750,
)
VIIRS_M9 = Channel(
    c_id="M9",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M9",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=1.378,
        bandwidth=0.015,
    ),
    resolution=750,
)
VIIRS_M10 = Channel(
    c_id="M10",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M10",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=1.610,
        bandwidth=0.060,
    ),
    resolution=750,
)
VIIRS_M11 = Channel(
    c_id="M11",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M11",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=2.250,
        bandwidth=0.050,
    ),
    resolution=750,
)
VIIRS_M12 = Channel(
    c_id="M12",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M12",
        band_type=BandType.get("Infrared"),
        central_wavelength=3.700,
        bandwidth=0.180,
    ),
    resolution=750,
)
VIIRS_M13 = Channel(
    c_id="M13",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M13",
        band_type=BandType.get("Infrared"),
        central_wavelength=4.050,
        bandwidth=0.155,
    ),
    resolution=750,
)
VIIRS_M14 = Channel(
    c_id="M14",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M14",
        band_type=BandType.get("Infrared"),
        central_wavelength=8.550,
        bandwidth=0.300,
    ),
    resolution=750,
)
VIIRS_M15 = Channel(
    c_id="M15",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M15",
        band_type=BandType.get("Infrared"),
        central_wavelength=10.763,
        bandwidth=1.000,
    ),
    resolution=750,
)
VIIRS_M16 = Channel(
    c_id="M16",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="M16",
        band_type=BandType.get("Infrared"),
        central_wavelength=12.013,
        bandwidth=0.950,
    ),
    resolution=750,
)
VIIRS_I1 = Channel(
    c_id="I1",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="I1",
        band_type=BandType.get("Visible"),
        central_wavelength=0.640,
        bandwidth=0.080,
    ),  # approx based on 0.60-0.68 range
    resolution=375,
)
VIIRS_I2 = Channel(
    c_id="I2",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="I2",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.865,
        bandwidth=0.039,
    ),  # approx based on 0.845-0.884
    resolution=375,
)
VIIRS_I3 = Channel(
    c_id="I3",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="I3",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=1.610,
        bandwidth=0.060,
    ),  # approx based on 1.58-1.64
    resolution=375,
)
VIIRS_I4 = Channel(
    c_id="I4",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="I4",
        band_type=BandType.get("Infrared"),
        central_wavelength=3.740,
        bandwidth=0.380,
    ),  # approx 3.55-3.93
    resolution=375,
)
VIIRS_I5 = Channel(
    c_id="I5",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="I5",
        band_type=BandType.get("Infrared"),
        central_wavelength=11.450,
        bandwidth=1.900,
    ),  # approx 10.5-12.4
    resolution=375,
)
VIIRS_DNB = Channel(
    c_id="DNB",
    instrument=Instrument.get("VIIRS"),
    band=Band(
        name="DNB",
        band_type=BandType.get("Day/Night"),
        central_wavelength=0.700,
        bandwidth=0.400,
    ),  # approx 0.5-0.9
    resolution=750,
)

VIIRS_CHANNELS = (
    VIIRS_M1,
    VIIRS_M2,
    VIIRS_M3,
    VIIRS_M4,
    VIIRS_M5,
    VIIRS_M6,
    VIIRS_M7,
    VIIRS_M8,
    VIIRS_M9,
    VIIRS_M10,
    VIIRS_M11,
    VIIRS_M12,
    VIIRS_M13,
    VIIRS_M14,
    VIIRS_M15,
    VIIRS_M16,
    VIIRS_I1,
    VIIRS_I2,
    VIIRS_I3,
    VIIRS_I4,
    VIIRS_I5,
    VIIRS_DNB,
)


def viirs_plugin() -> None:
    pass
