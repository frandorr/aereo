from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AerModel(BaseModel):
    """Base class for all repository models."""

    model_config = ConfigDict(from_attributes=True)


# ==========================================
#  MajorTOM Grid models
# ==========================================


class GridDefinition(AerModel):
    """Domain model for a grid definition.

    Contains only business-relevant fields. UUID generation
    is handled by repository implementations.
    """

    majortom_grid_name: str
    distance_km: float
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float


class GridCell(AerModel):
    """Domain model for a grid cell.

    Contains only business-relevant fields. UUID generation
    is handled by repository implementations.
    """

    cell_bounds: (
        Any  # Can be a shapely geometry or WKT/WKB string depending on implementation
    )
    area_def: str
    utm_region: str


# ==========================================
#  Search space models
# ==========================================


class Asset(AerModel):
    """Domain model for an asset.

    Contains only business-relevant fields. UUID generation
    is handled by repository implementations.
    """

    provider: str
    s3_url: str | None = None
    http_url: str | None = None
    timestamp: datetime


# ==========================================
#  Extraction space models
# ==========================================


class Derivative(AerModel):
    """Domain model for a derivative.

    Contains only business-relevant fields. UUID generation
    is handled by repository implementations.
    """

    name: str
    local_path: str
    version: str
    algorithm_name: str
    creation_date: datetime


# ==========================================
#  Satellites, Instruments & Channels models
# ==========================================


class Satellite(AerModel):
    satellite_id: str
    satellite_name: str
    organization: str


class Instrument(AerModel):
    instrument_id: str
    instrument_name: str
    sensor_type: str


class Channel(AerModel):
    channel_id: str
    instrument_id: str
    satellite_id: str
    channel_name: str
    wavelength_central: float
    wavelength_unit: str
