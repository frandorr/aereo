from aer.spectral import Band, BandType, Channel, Instrument, Satellite

# Register Sentinel-3 sats and instruments
Instrument.register("OLCI", "https://space.oscar.wmo.int/instruments/view/olci")
Instrument.register("SLSTR", "https://space.oscar.wmo.int/instruments/view/slstr")
Satellite.register(
    "SENTINEL-3A", "https://space.oscar.wmo.int/satellites/view/sentinel-3a"
)
Satellite.register(
    "SENTINEL-3B", "https://space.oscar.wmo.int/satellites/view/sentinel-3b"
)

SENTINEL_3_CONSTELLATION = frozenset(
    [Satellite.get("SENTINEL-3A"), Satellite.get("SENTINEL-3B")]
)

OLCI_BAND_Oa01 = Channel(
    c_id="Oa01",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa01",
        band_type=BandType.get("Visible"),
        central_wavelength=0.4,
        bandwidth=0.015,
    ),
    resolution=300,
)
OLCI_BAND_Oa02 = Channel(
    c_id="Oa02",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa02",
        band_type=BandType.get("Visible"),
        central_wavelength=0.4125,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa03 = Channel(
    c_id="Oa03",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa03",
        band_type=BandType.get("Visible"),
        central_wavelength=0.4425,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa04 = Channel(
    c_id="Oa04",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa04",
        band_type=BandType.get("Visible"),
        central_wavelength=0.49,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa05 = Channel(
    c_id="Oa05",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa05",
        band_type=BandType.get("Visible"),
        central_wavelength=0.51,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa06 = Channel(
    c_id="Oa06",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa06",
        band_type=BandType.get("Visible"),
        central_wavelength=0.56,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa07 = Channel(
    c_id="Oa07",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa07",
        band_type=BandType.get("Visible"),
        central_wavelength=0.62,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa08 = Channel(
    c_id="Oa08",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa08",
        band_type=BandType.get("Visible"),
        central_wavelength=0.665,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa09 = Channel(
    c_id="Oa09",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa09",
        band_type=BandType.get("Visible"),
        central_wavelength=0.67375,
        bandwidth=0.0075,
    ),
    resolution=300,
)
OLCI_BAND_Oa10 = Channel(
    c_id="Oa10",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa10",
        band_type=BandType.get("Visible"),
        central_wavelength=0.68125,
        bandwidth=0.0075,
    ),
    resolution=300,
)
OLCI_BAND_Oa11 = Channel(
    c_id="Oa11",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa11",
        band_type=BandType.get("Visible"),
        central_wavelength=0.70875,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa12 = Channel(
    c_id="Oa12",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa12",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.75375,
        bandwidth=0.0075,
    ),
    resolution=300,
)
OLCI_BAND_Oa13 = Channel(
    c_id="Oa13",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa13",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.76125,
        bandwidth=0.0025,
    ),
    resolution=300,
)
OLCI_BAND_Oa14 = Channel(
    c_id="Oa14",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa14",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.764375,
        bandwidth=0.00375,
    ),
    resolution=300,
)
OLCI_BAND_Oa15 = Channel(
    c_id="Oa15",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa15",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.7675,
        bandwidth=0.0025,
    ),
    resolution=300,
)
OLCI_BAND_Oa16 = Channel(
    c_id="Oa16",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa16",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.77875,
        bandwidth=0.015,
    ),
    resolution=300,
)
OLCI_BAND_Oa17 = Channel(
    c_id="Oa17",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa17",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.865,
        bandwidth=0.02,
    ),
    resolution=300,
)
OLCI_BAND_Oa18 = Channel(
    c_id="Oa18",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa18",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.885,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa19 = Channel(
    c_id="Oa19",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa19",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.9,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa20 = Channel(
    c_id="Oa20",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa20",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.94,
        bandwidth=0.02,
    ),
    resolution=300,
)
OLCI_BAND_Oa21 = Channel(
    c_id="Oa21",
    instrument=Instrument.get("OLCI"),
    band=Band(
        name="Oa21",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=1.02,
        bandwidth=0.04,
    ),
    resolution=300,
)

OLCI_CHANNELS = (
    OLCI_BAND_Oa01,
    OLCI_BAND_Oa02,
    OLCI_BAND_Oa03,
    OLCI_BAND_Oa04,
    OLCI_BAND_Oa05,
    OLCI_BAND_Oa06,
    OLCI_BAND_Oa07,
    OLCI_BAND_Oa08,
    OLCI_BAND_Oa09,
    OLCI_BAND_Oa10,
    OLCI_BAND_Oa11,
    OLCI_BAND_Oa12,
    OLCI_BAND_Oa13,
    OLCI_BAND_Oa14,
    OLCI_BAND_Oa15,
    OLCI_BAND_Oa16,
    OLCI_BAND_Oa17,
    OLCI_BAND_Oa18,
    OLCI_BAND_Oa19,
    OLCI_BAND_Oa20,
    OLCI_BAND_Oa21,
)

SLSTR_BAND_S1 = Channel(
    c_id="S1",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="S1",
        band_type=BandType.get("Visible"),
        central_wavelength=0.55427,
        bandwidth=0.01926,
    ),
    resolution=500,
)
SLSTR_BAND_S2 = Channel(
    c_id="S2",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="S2",
        band_type=BandType.get("Visible"),
        central_wavelength=0.65947,
        bandwidth=0.01925,
    ),
    resolution=500,
)
SLSTR_BAND_S3 = Channel(
    c_id="S3",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="S3",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=0.868,
        bandwidth=0.0206,
    ),
    resolution=500,
)
SLSTR_BAND_S4 = Channel(
    c_id="S4",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="S4",
        band_type=BandType.get("Near-Infrared"),
        central_wavelength=1.3748,
        bandwidth=0.0208,
    ),
    resolution=500,
)
SLSTR_BAND_S5 = Channel(
    c_id="S5",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="S5",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=1.6134,
        bandwidth=0.06068,
    ),
    resolution=500,
)
SLSTR_BAND_S6 = Channel(
    c_id="S6",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="S6",
        band_type=BandType.get("Shortwave Infrared"),
        central_wavelength=2.2557,
        bandwidth=0.05015,
    ),
    resolution=500,
)
SLSTR_BAND_S7 = Channel(
    c_id="S7",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="S7",
        band_type=BandType.get("Infrared"),
        central_wavelength=3.742,
        bandwidth=0.398,
    ),
    resolution=1000,
)
SLSTR_BAND_S8 = Channel(
    c_id="S8",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="S8",
        band_type=BandType.get("Infrared"),
        central_wavelength=10.854,
        bandwidth=0.776,
    ),
    resolution=1000,
)
SLSTR_BAND_S9 = Channel(
    c_id="S9",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="S9",
        band_type=BandType.get("Infrared"),
        central_wavelength=12.0225,
        bandwidth=0.905,
    ),
    resolution=1000,
)
SLSTR_BAND_F1 = Channel(
    c_id="F1",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="F1",
        band_type=BandType.get("Infrared"),
        central_wavelength=3.742,
        bandwidth=0.398,
    ),
    resolution=1000,
)
SLSTR_BAND_F2 = Channel(
    c_id="F2",
    instrument=Instrument.get("SLSTR"),
    band=Band(
        name="F2",
        band_type=BandType.get("Infrared"),
        central_wavelength=10.854,
        bandwidth=0.776,
    ),
    resolution=1000,
)

SLSTR_CHANNELS = (
    SLSTR_BAND_S1,
    SLSTR_BAND_S2,
    SLSTR_BAND_S3,
    SLSTR_BAND_S4,
    SLSTR_BAND_S5,
    SLSTR_BAND_S6,
    SLSTR_BAND_S7,
    SLSTR_BAND_S8,
    SLSTR_BAND_S9,
    SLSTR_BAND_F1,
    SLSTR_BAND_F2,
)


def sentinel3_plugin() -> None:
    pass
