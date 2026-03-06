from aer.spectral import Band, BandType, Channel, Instrument, Satellite

# Register GOES sat and instrument
Instrument.register("ABI", "https://space.oscar.wmo.int/instruments/view/abi")
Satellite.register("GOES-16", "https://space.oscar.wmo.int/satellites/view/goes-16")
Satellite.register("GOES-18", "https://space.oscar.wmo.int/satellites/view/goes-18")
Satellite.register("GOES-19", "https://space.oscar.wmo.int/satellites/view/goes-19")

GOES_CONSTELLATION = frozenset(
    [Satellite.get("GOES-16"), Satellite.get("GOES-18"), Satellite.get("GOES-19")]
)

ABI_BAND_1 = Channel(
    c_id="1",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Blue",
        band_type=BandType.get("Visible"),
        central_wavelength=0.47,
        bandwidth=0.04,
    ),
    resolution=1000,
)
ABI_BAND_2 = Channel(
    c_id="2",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Red",
        band_type=BandType.get("Visible"),
        central_wavelength=0.64,
        bandwidth=0.10,
    ),
    resolution=500,
)
ABI_BAND_3 = Channel(
    c_id="3",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Veggie",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.86,
        bandwidth=0.04,
    ),
    resolution=1000,
)
ABI_BAND_4 = Channel(
    c_id="4",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Cirrus",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=1.38,
        bandwidth=0.03,
    ),
    resolution=2000,
)
ABI_BAND_5 = Channel(
    c_id="5",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Snow/Ice",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=1.61,
        bandwidth=0.06,
    ),
    resolution=1000,
)
ABI_BAND_6 = Channel(
    c_id="6",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Cloud particle size",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=2.26,
        bandwidth=0.05,
    ),
    resolution=2000,
)
ABI_BAND_7 = Channel(
    c_id="7",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Shortwave window",
        band_type=BandType.get("Infrared"),
        central_wavelength=3.90,
        bandwidth=0.20,
    ),
    resolution=2000,
)
ABI_BAND_8 = Channel(
    c_id="8",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Upper-level water vapor",
        band_type=BandType.get("Infrared"),
        central_wavelength=6.15,
        bandwidth=0.90,
    ),
    resolution=2000,
)
ABI_BAND_9 = Channel(
    c_id="9",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Midlevel water vapor",
        band_type=BandType.get("Infrared"),
        central_wavelength=7.00,
        bandwidth=0.40,
    ),
    resolution=2000,
)
ABI_BAND_10 = Channel(
    c_id="10",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Lower-level water vapor",
        band_type=BandType.get("Infrared"),
        central_wavelength=7.40,
        bandwidth=0.20,
    ),
    resolution=2000,
)
ABI_BAND_11 = Channel(
    c_id="11",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Cloud-top phase",
        band_type=BandType.get("Infrared"),
        central_wavelength=8.50,
        bandwidth=0.40,
    ),
    resolution=2000,
)
ABI_BAND_12 = Channel(
    c_id="12",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Ozone",
        band_type=BandType.get("Infrared"),
        central_wavelength=9.70,
        bandwidth=0.20,
    ),
    resolution=2000,
)
ABI_BAND_13 = Channel(
    c_id="13",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Clean longwave window",
        band_type=BandType.get("Infrared"),
        central_wavelength=10.3,
        bandwidth=0.50,
    ),
    resolution=2000,
)
ABI_BAND_14 = Channel(
    c_id="14",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Longwave window",
        band_type=BandType.get("Infrared"),
        central_wavelength=11.2,
        bandwidth=0.80,
    ),
    resolution=2000,
)
ABI_BAND_15 = Channel(
    c_id="15",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="Dirty longwave window",
        band_type=BandType.get("Infrared"),
        central_wavelength=12.3,
        bandwidth=1.00,
    ),
    resolution=2000,
)
ABI_BAND_16 = Channel(
    c_id="16",
    instrument=Instrument.get("ABI"),
    band=Band(
        name="CO2 longwave",
        band_type=BandType.get("Infrared"),
        central_wavelength=13.3,
        bandwidth=0.60,
    ),
    resolution=2000,
)

ABI_CHANNELS = (
    ABI_BAND_1,
    ABI_BAND_2,
    ABI_BAND_3,
    ABI_BAND_4,
    ABI_BAND_5,
    ABI_BAND_6,
    ABI_BAND_7,
    ABI_BAND_8,
    ABI_BAND_9,
    ABI_BAND_10,
    ABI_BAND_11,
    ABI_BAND_12,
    ABI_BAND_13,
    ABI_BAND_14,
    ABI_BAND_15,
    ABI_BAND_16,
)


def goes_plugin() -> None:
    pass
