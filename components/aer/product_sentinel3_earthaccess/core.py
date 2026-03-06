from aer.spectral import Instrument, Product, Satellite
from aer.spectral_sentinel3 import OLCI_CHANNELS, SLSTR_CHANNELS

# Sentinel-3 Products
SENTINEL_3_OLCI_1_EFR_NRT_EA = Product(
    name="sentinel-3-olci-1-efr-nrt",
    instrument=Instrument.get("OLCI"),
    supported_satellites=frozenset(
        [Satellite.get("SENTINEL-3A"), Satellite.get("SENTINEL-3B")]
    ),
    channels=OLCI_CHANNELS,
)

SENTINEL_3_OLCI_1_EFR_NTC_EA = Product(
    name="sentinel-3-olci-1-efr-ntc",
    instrument=Instrument.get("OLCI"),
    supported_satellites=frozenset(
        [Satellite.get("SENTINEL-3A"), Satellite.get("SENTINEL-3B")]
    ),
    channels=OLCI_CHANNELS,
)

SENTINEL_3_SLSTR_1_RBT_NRT_EA = Product(
    name="sentinel-3-slstr-1-rbt-nrt",
    instrument=Instrument.get("SLSTR"),
    supported_satellites=frozenset(
        [Satellite.get("SENTINEL-3A"), Satellite.get("SENTINEL-3B")]
    ),
    channels=SLSTR_CHANNELS,
)

SENTINEL_3_SLSTR_1_RBT_NTC_EA = Product(
    name="sentinel-3-slstr-1-rbt-ntc",
    instrument=Instrument.get("SLSTR"),
    supported_satellites=frozenset(
        [Satellite.get("SENTINEL-3A"), Satellite.get("SENTINEL-3B")]
    ),
    channels=SLSTR_CHANNELS,
)


def sentinel3_earthaccess_plugin() -> None:
    pass
