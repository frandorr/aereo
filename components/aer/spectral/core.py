"""Core spectral data models and channel factory.

Defines typed channel classes (OpticalChannel, MicrowaveChannel,
SARChannel, SpectrometerChannel), Instrument and Satellite models,
and the create_channel() factory for constructing channels from
normalized WMO OSCAR data.
"""

from typing import Any, Sequence, Union

import attrs
import cattrs


# ==========================================
#  Channel Models
# ==========================================
@attrs.frozen(kw_only=True)
class BaseChannel:
    channel_name: str
    unit: str | None = None


@attrs.frozen(kw_only=True)
class OpticalChannel(BaseChannel):
    central_wavelength: float
    bandwidth: float
    spatial_resolution: float
    snr_low: float | str | None = None
    snr_high: float | str | None = None
    snr_or_nedt: float | str | None = None


@attrs.frozen(kw_only=True)
class MicrowaveChannel(BaseChannel):
    central_frequency: float
    bandwidth: float
    spatial_resolution: float
    polarisations: str | None = None
    nedt: float | None = None


@attrs.frozen(kw_only=True)
class SARChannel(BaseChannel):
    operation_mode: str
    spatial_resolution: float | tuple[float, float]
    swath_width: float | tuple[float, float] | None = None
    polarisation: str | None = None
    field_of_regard: float | tuple[float, float] | str | None = None


@attrs.frozen(kw_only=True)
class SpectrometerChannel(BaseChannel):
    wave_number_min: float
    wave_number_max: float
    spectral_resolution: float
    number_of_channels: float | None = None
    snr_or_nedt: float | str | None = None


ChannelType = Union[OpticalChannel, MicrowaveChannel, SARChannel, SpectrometerChannel]


# ==========================================
#  Satellites & Instruments Models
# ==========================================
@attrs.frozen(repr=False)
class Instrument:
    acronym: str
    channels: Sequence[ChannelType]
    metadata: dict[str, Any] | None = None

    def __repr__(self) -> str:
        lines = [f"Instrument: {self.acronym}"]
        for key, value in (self.metadata or {}).items():
            lines.append(f"  {key.capitalize()}: {value}")
        lines.append(f"└─ Channels ({len(self.channels)}):")
        for ch in self.channels:
            lines.append(f"   - {repr(ch)}")
        return "\n".join(lines)


@attrs.frozen(repr=False)
class Satellite:
    acronym: str
    payload: list[Instrument]
    metadata: dict[str, Any] | None = None

    def __repr__(self) -> str:
        lines = [f"Satellite({self.acronym})"]
        lines.append(f"  └─ Payload ({len(self.payload)} instruments):")

        for inst in self.payload:
            inst_repr = repr(inst)
            indented_inst = "\n".join(f"     {line}" for line in inst_repr.split("\n"))
            lines.append(indented_inst)
        for key, value in (self.metadata or {}).items():
            lines.append(f"  {key.capitalize()}: {value}")

        return "\n".join(lines)


# ==========================================
#  Cattrs Converters for Custom Structuring
# ==========================================

converter = cattrs.Converter()


def _structure_float_str_none(val: Any, _type: Any) -> float | str | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    return str(val)


def _structure_float_tuple(val: Any, _type: Any) -> float | tuple[float, float]:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, (list, tuple)) and len(val) == 2:
        return (float(val[0]), float(val[1]))
    raise ValueError(f"Cannot structure {val} as float or tuple[float, float]")


converter.register_structure_hook(
    Union[float, str, type(None)], _structure_float_str_none
)
converter.register_structure_hook(
    Union[float, tuple[float, float]], _structure_float_tuple
)
converter.register_structure_hook(
    Union[float, tuple[float, float], type(None)],
    lambda val, t: None if val is None else _structure_float_tuple(val, t),
)


def _structure_float_tuple_str_none(
    val: Any, _type: Any
) -> float | tuple[float, float] | str | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, (list, tuple)) and len(val) == 2:
        return (float(val[0]), float(val[1]))
    return str(val)


converter.register_structure_hook(
    Union[float, tuple[float, float], str, type(None)], _structure_float_tuple_str_none
)


def create_channel(schema_type: str, data: dict[str, Any]) -> ChannelType:
    struct_data = dict(data)

    if schema_type == "optical_infrared":
        return converter.structure(struct_data, OpticalChannel)
    elif schema_type == "microwave":
        return converter.structure(struct_data, MicrowaveChannel)
    elif schema_type == "sar_active":
        return converter.structure(struct_data, SARChannel)
    elif schema_type == "spectrometer_sounder":
        return converter.structure(struct_data, SpectrometerChannel)
    else:
        raise ValueError(f"Unknown schema_type: {schema_type}")
