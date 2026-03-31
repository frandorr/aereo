from typing import Any

import attrs
from aer.spectral import Instrument, Satellite
from shapely.geometry import Polygon


@attrs.frozen
class Product:
    product_id: str
    processing_level: str
    instruments: list[Instrument]
    satellites: list[Satellite]
    metadata: dict[str, Any] = {}


@attrs.frozen
class AssetVariable:
    name: str  # The actual name of the variable in the file (e.g., 'CMI', 'Mask', 'latitude')
    role: str  # e.g., 'channel', 'mask', 'geolocation', 'quality_flag', 'generic'

    # Optional metadata dictionary to hold type-specific information
    # - For a channel: {"channel": Channel}
    # - For a mask: {"flag_meanings": {0: "water", 1: "fire", 2: "cloud"}}
    metadata: dict[str, Any] = attrs.field(factory=dict)


@attrs.frozen
class Asset:
    product: Product
    url: str
    spatial_coverage: Polygon
    variables: list[AssetVariable] = attrs.field(factory=list)

    # Optional metadata dictionary to hold asset-specific metadata
    # e.g. {"cloud_hosted": True}
    metadata: dict[str, Any] = attrs.field(factory=dict)
