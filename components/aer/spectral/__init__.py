"""
spectral defines the canonical, instrument-agnostic data model for
spectral measurements used across the system.
It provides the structural types, typestate markers, and taxonomy primitives required
to represent Earth observation bands in a consistent and type-safe way.

This component contains no IO, no satellite-specific logic, and no transformation algorithms.
It encodes structure and invariants only.
"""

from aer.spectral.core import (
    Band,
    BandType,
    Channel,
    ChannelType,
    Instrument,
    Product,
    Satellite,
    create_channel,
    BaseChannel,
    OpticalChannel,
    MicrowaveChannel,
    SARChannel,
    SpectrometerChannel,
)

__all__ = [
    "Band",
    "BandType",
    "Channel",
    "ChannelType",
    "Instrument",
    "Product",
    "Satellite",
    "create_channel",
    "BaseChannel",
    "OpticalChannel",
    "MicrowaveChannel",
    "SARChannel",
    "SpectrometerChannel",
]
