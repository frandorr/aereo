from aer.spectral import Instrument, Product, Satellite
from aer.spectral_viirs import (
    VIIRS_DNB,
    VIIRS_I1,
    VIIRS_I2,
    VIIRS_I3,
    VIIRS_I4,
    VIIRS_I5,
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
)

# VIIRS S-NPP Products
VNP02IMG_EA = Product(
    name="VNP02IMG",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("SNPP")]),
    channels=(VIIRS_I1, VIIRS_I2, VIIRS_I3, VIIRS_I4, VIIRS_I5),
)

VNP03IMG_EA = Product(
    name="VNP03IMG",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("SNPP")]),
    channels=(),
)

VNP02MOD_EA = Product(
    name="VNP02MOD",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("SNPP")]),
    channels=(
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
    ),
)

VNP03MOD_EA = Product(
    name="VNP03MOD",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("SNPP")]),
    channels=(),
)

VNP02DNB_EA = Product(
    name="VNP02DNB",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("SNPP")]),
    channels=(VIIRS_DNB,),
)

VNP03DNB_EA = Product(
    name="VNP03DNB",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("SNPP")]),
    channels=(),
)

# VIIRS NOAA-20 Products
VJ102IMG_EA = Product(
    name="VJ102IMG",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-20")]),
    channels=(VIIRS_I1, VIIRS_I2, VIIRS_I3, VIIRS_I4, VIIRS_I5),
)

VJ103IMG_EA = Product(
    name="VJ103IMG",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-20")]),
    channels=(),
)

VJ102MOD_EA = Product(
    name="VJ102MOD",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-20")]),
    channels=(
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
    ),
)

VJ103MOD_EA = Product(
    name="VJ103MOD",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-20")]),
    channels=(),
)

VJ102DNB_EA = Product(
    name="VJ102DNB",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-20")]),
    channels=(VIIRS_DNB,),
)

VJ103DNB_EA = Product(
    name="VJ103DNB",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-20")]),
    channels=(),
)

# VIIRS NOAA-21 Products
VJ202IMG_EA = Product(
    name="VJ202IMG",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-21")]),
    channels=(VIIRS_I1, VIIRS_I2, VIIRS_I3, VIIRS_I4, VIIRS_I5),
)

VJ203IMG_EA = Product(
    name="VJ203IMG",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-21")]),
    channels=(),
)

VJ202MOD_EA = Product(
    name="VJ202MOD",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-21")]),
    channels=(
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
    ),
)

VJ203MOD_EA = Product(
    name="VJ203MOD",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-21")]),
    channels=(),
)

VJ202DNB_EA = Product(
    name="VJ202DNB",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-21")]),
    channels=(VIIRS_DNB,),
)

VJ203DNB_EA = Product(
    name="VJ203DNB",
    instrument=Instrument.get("VIIRS"),
    supported_satellites=frozenset([Satellite.get("NOAA-21")]),
    channels=(),
)


def viirs_earthaccess_plugin() -> None:
    pass
