import attrs


# ==========================================
#  Satellites, Instruments & Channels models
# ==========================================
@attrs.frozen
class Channel:
    instrument_acronym: str
    central_wavelength: float
    bandwidth: float
    unit: str
    resolution_m: float


@attrs.frozen
class Instrument:
    satellite_acronym: str
    acronym: str
    channels: list[Channel]


@attrs.frozen
class Satellite:
    acronym: str
    payload: list[Instrument]
