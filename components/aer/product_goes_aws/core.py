from aer.spectral import Instrument, Product
from aer.spectral_goes import ABI_CHANNELS, GOES_CONSTELLATION


# ABI Products on AWS
ABI_L1B_RADF_AWS = Product(
    name="ABI-L1b-RadF",
    instrument=Instrument.get("ABI"),
    supported_satellites=GOES_CONSTELLATION,
    channels=ABI_CHANNELS,
)

ABI_L1B_RADC_AWS = Product(
    name="ABI-L1b-RadC",
    instrument=Instrument.get("ABI"),
    supported_satellites=GOES_CONSTELLATION,
    channels=ABI_CHANNELS,
)

ABI_L1B_RADM_AWS = Product(
    name="ABI-L1b-RadM",
    instrument=Instrument.get("ABI"),
    supported_satellites=GOES_CONSTELLATION,
    channels=ABI_CHANNELS,
)


def goes_aws_plugin() -> None:
    pass
