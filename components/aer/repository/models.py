import attrs


# ==========================================
#  Satellites, Instruments & Channels models
# ==========================================
@attrs.frozen
class Channel:
    central_wavelength: float
    bandwidth: float
    unit: str
    resolution_m: float


@attrs.frozen
class Instrument:
    acronym: str
    channels: list[Channel]


@attrs.frozen
class Satellite:
    acronym: str
    payload: list[Instrument]
