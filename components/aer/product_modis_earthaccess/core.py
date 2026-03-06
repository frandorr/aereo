from aer.spectral import Instrument, Product, Satellite
from aer.spectral_modis import (
    MODIS_BAND_1,
    MODIS_BAND_2,
    MODIS_BAND_3,
    MODIS_BAND_4,
    MODIS_BAND_5,
    MODIS_BAND_6,
    MODIS_BAND_7,
    MODIS_CHANNELS,
)

# MODIS Products
MODIS_02QKM_EA = Product(
    name="MOD02QKM",
    instrument=Instrument.get("MODIS"),
    supported_satellites=frozenset([Satellite.get("TERRA")]),
    channels=(MODIS_BAND_1, MODIS_BAND_2),
)

MODIS_02HKM_EA = Product(
    name="MOD02HKM",
    instrument=Instrument.get("MODIS"),
    supported_satellites=frozenset([Satellite.get("TERRA")]),
    channels=(
        MODIS_BAND_1,
        MODIS_BAND_2,
        MODIS_BAND_3,
        MODIS_BAND_4,
        MODIS_BAND_5,
        MODIS_BAND_6,
        MODIS_BAND_7,
    ),
)

MODIS_021KM_EA = Product(
    name="MOD021KM",
    instrument=Instrument.get("MODIS"),
    supported_satellites=frozenset([Satellite.get("TERRA")]),
    channels=MODIS_CHANNELS,
)

MYDIS_02QKM_EA = Product(
    name="MYD02QKM",
    instrument=Instrument.get("MODIS"),
    supported_satellites=frozenset([Satellite.get("AQUA")]),
    channels=(MODIS_BAND_1, MODIS_BAND_2),
)

MYDIS_02HKM_EA = Product(
    name="MYD02HKM",
    instrument=Instrument.get("MODIS"),
    supported_satellites=frozenset([Satellite.get("AQUA")]),
    channels=(
        MODIS_BAND_1,
        MODIS_BAND_2,
        MODIS_BAND_3,
        MODIS_BAND_4,
        MODIS_BAND_5,
        MODIS_BAND_6,
        MODIS_BAND_7,
    ),
)

MYDIS_021KM_EA = Product(
    name="MYD021KM",
    instrument=Instrument.get("MODIS"),
    supported_satellites=frozenset([Satellite.get("AQUA")]),
    channels=MODIS_CHANNELS,
)


def modis_earthaccess_plugin() -> None:
    pass
