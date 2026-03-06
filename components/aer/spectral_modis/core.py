from aer.spectral import Band, BandType, Channel, Instrument, Satellite

# Register MODIS sats and instrument
Instrument.register("MODIS", "https://space.oscar.wmo.int/instruments/view/modis")
Satellite.register("TERRA", "https://space.oscar.wmo.int/satellites/view/terra")
Satellite.register("AQUA", "https://space.oscar.wmo.int/satellites/view/aqua")

MODIS_CONSTELLATION = frozenset([Satellite.get("TERRA"), Satellite.get("AQUA")])

MODIS_BAND_1 = Channel(
    c_id="1",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="1",
        band_type=BandType.get("Visible"),
        central_wavelength=0.645,
        bandwidth=0.050,
    ),
    resolution=250,
)
MODIS_BAND_2 = Channel(
    c_id="2",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="2",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.858,
        bandwidth=0.035,
    ),
    resolution=250,
)
MODIS_BAND_3 = Channel(
    c_id="3",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="3",
        band_type=BandType.get("Visible"),
        central_wavelength=0.469,
        bandwidth=0.020,
    ),
    resolution=500,
)
MODIS_BAND_4 = Channel(
    c_id="4",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="4",
        band_type=BandType.get("Visible"),
        central_wavelength=0.555,
        bandwidth=0.020,
    ),
    resolution=500,
)
MODIS_BAND_5 = Channel(
    c_id="5",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="5",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=1.240,
        bandwidth=0.020,
    ),
    resolution=500,
)
MODIS_BAND_6 = Channel(
    c_id="6",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="6",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=1.640,
        bandwidth=0.024,
    ),
    resolution=500,
)
MODIS_BAND_7 = Channel(
    c_id="7",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="7",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=2.130,
        bandwidth=0.050,
    ),
    resolution=500,
)
MODIS_BAND_8 = Channel(
    c_id="8",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="8",
        band_type=BandType.get("Visible"),
        central_wavelength=0.412,
        bandwidth=0.015,
    ),
    resolution=1000,
)
MODIS_BAND_9 = Channel(
    c_id="9",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="9",
        band_type=BandType.get("Visible"),
        central_wavelength=0.443,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_10 = Channel(
    c_id="10",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="10",
        band_type=BandType.get("Visible"),
        central_wavelength=0.488,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_11 = Channel(
    c_id="11",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="11",
        band_type=BandType.get("Visible"),
        central_wavelength=0.531,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_12 = Channel(
    c_id="12",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="12",
        band_type=BandType.get("Visible"),
        central_wavelength=0.551,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_13h = Channel(
    c_id="13h",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="13h",
        band_type=BandType.get("Visible"),
        central_wavelength=0.667,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_13l = Channel(
    c_id="13l",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="13l",
        band_type=BandType.get("Visible"),
        central_wavelength=0.667,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_14h = Channel(
    c_id="14h",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="14h",
        band_type=BandType.get("Visible"),
        central_wavelength=0.678,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_14l = Channel(
    c_id="14l",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="14l",
        band_type=BandType.get("Visible"),
        central_wavelength=0.678,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_15 = Channel(
    c_id="15",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="15",
        band_type=BandType.get("Visible"),
        central_wavelength=0.748,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_16 = Channel(
    c_id="16",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="16",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.870,
        bandwidth=0.015,
    ),
    resolution=1000,
)
MODIS_BAND_17 = Channel(
    c_id="17",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="17",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.905,
        bandwidth=0.030,
    ),
    resolution=1000,
)
MODIS_BAND_18 = Channel(
    c_id="18",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="18",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.936,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_19 = Channel(
    c_id="19",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="19",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.940,
        bandwidth=0.050,
    ),
    resolution=1000,
)
MODIS_BAND_20 = Channel(
    c_id="20",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="20",
        band_type=BandType.get("Infrared"),
        central_wavelength=3.750,
        bandwidth=0.180,
    ),
    resolution=1000,
)
MODIS_BAND_21 = Channel(
    c_id="21",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="21",
        band_type=BandType.get("Infrared"),
        central_wavelength=3.959,
        bandwidth=0.060,
    ),
    resolution=1000,
)
MODIS_BAND_22 = Channel(
    c_id="22",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="22",
        band_type=BandType.get("Infrared"),
        central_wavelength=3.959,
        bandwidth=0.060,
    ),
    resolution=1000,
)
MODIS_BAND_23 = Channel(
    c_id="23",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="23",
        band_type=BandType.get("Infrared"),
        central_wavelength=4.050,
        bandwidth=0.060,
    ),
    resolution=1000,
)
MODIS_BAND_24 = Channel(
    c_id="24",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="24",
        band_type=BandType.get("Infrared"),
        central_wavelength=4.515,
        bandwidth=0.165,
    ),
    resolution=1000,
)
MODIS_BAND_25 = Channel(
    c_id="25",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="25",
        band_type=BandType.get("Infrared"),
        central_wavelength=4.515,
        bandwidth=0.067,
    ),
    resolution=1000,
)
MODIS_BAND_26 = Channel(
    c_id="26",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="26",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=1.375,
        bandwidth=0.030,
    ),
    resolution=1000,
)
MODIS_BAND_27 = Channel(
    c_id="27",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="27",
        band_type=BandType.get("Infrared"),
        central_wavelength=6.715,
        bandwidth=0.360,
    ),
    resolution=1000,
)
MODIS_BAND_28 = Channel(
    c_id="28",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="28",
        band_type=BandType.get("Infrared"),
        central_wavelength=7.325,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_29 = Channel(
    c_id="29",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="29",
        band_type=BandType.get("Infrared"),
        central_wavelength=8.550,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_30 = Channel(
    c_id="30",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="30",
        band_type=BandType.get("Infrared"),
        central_wavelength=9.730,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_31 = Channel(
    c_id="31",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="31",
        band_type=BandType.get("Infrared"),
        central_wavelength=11.030,
        bandwidth=0.500,
    ),
    resolution=1000,
)
MODIS_BAND_32 = Channel(
    c_id="32",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="32",
        band_type=BandType.get("Infrared"),
        central_wavelength=12.020,
        bandwidth=0.500,
    ),
    resolution=1000,
)
MODIS_BAND_33 = Channel(
    c_id="33",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="33",
        band_type=BandType.get("Infrared"),
        central_wavelength=13.335,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_34 = Channel(
    c_id="34",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="34",
        band_type=BandType.get("Infrared"),
        central_wavelength=13.635,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_35 = Channel(
    c_id="35",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="35",
        band_type=BandType.get("Infrared"),
        central_wavelength=13.935,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_36 = Channel(
    c_id="36",
    instrument=Instrument.get("MODIS"),
    band=Band(
        name="36",
        band_type=BandType.get("Infrared"),
        central_wavelength=14.235,
        bandwidth=0.300,
    ),
    resolution=1000,
)

MODIS_CHANNELS = (
    MODIS_BAND_1,
    MODIS_BAND_2,
    MODIS_BAND_3,
    MODIS_BAND_4,
    MODIS_BAND_5,
    MODIS_BAND_6,
    MODIS_BAND_7,
    MODIS_BAND_8,
    MODIS_BAND_9,
    MODIS_BAND_10,
    MODIS_BAND_11,
    MODIS_BAND_12,
    MODIS_BAND_13h,
    MODIS_BAND_13l,
    MODIS_BAND_14h,
    MODIS_BAND_14l,
    MODIS_BAND_15,
    MODIS_BAND_16,
    MODIS_BAND_17,
    MODIS_BAND_18,
    MODIS_BAND_19,
    MODIS_BAND_20,
    MODIS_BAND_21,
    MODIS_BAND_22,
    MODIS_BAND_23,
    MODIS_BAND_24,
    MODIS_BAND_25,
    MODIS_BAND_26,
    MODIS_BAND_27,
    MODIS_BAND_28,
    MODIS_BAND_29,
    MODIS_BAND_30,
    MODIS_BAND_31,
    MODIS_BAND_32,
    MODIS_BAND_33,
    MODIS_BAND_34,
    MODIS_BAND_35,
    MODIS_BAND_36,
)


def modis_plugin() -> None:
    pass
