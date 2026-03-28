from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID

from aer.repository.models import (
    Asset,
    Channel,
    Derivative,
    GridCell,
    GridDefinition,
    Instrument,
    Satellite,
)


class AerRepository(ABC):
    """Abstract Base Class defining the Aer data access interface.

    This repository orchestrates persistence and retrieval across several
    conceptual spaces based on the Aer Entity-Relationship schema.
    """

    # ==========================================
    #  MajorTOM Grid methods
    # ==========================================

    @abstractmethod
    def create_grid_definition(
        self,
        majortom_grid_name: str,
        distance_km: float,
        min_latitude: float,
        max_latitude: float,
        min_longitude: float,
        max_longitude: float,
    ) -> UUID:
        """Create a new grid definition and return its UUID."""
        pass

    @abstractmethod
    def get_grid_definition(self, definition_id: UUID) -> GridDefinition | None:
        """Retrieve a grid definition by its UUID."""
        pass

    @abstractmethod
    def get_grid_definition_by_name(
        self, majortom_grid_name: str
    ) -> GridDefinition | None:
        """Retrieve a grid definition by its majortom_grid_name."""
        pass

    @abstractmethod
    def create_grid_cell(
        self,
        definition_id: UUID,
        cell_bounds: Any,  # GEOMETRY
        area_def: str,
        utm_region: str,
    ) -> UUID:
        """Create a new grid cell and return its UUID."""
        pass

    @abstractmethod
    def get_grid_cells_by_definition(
        self,
        definition_id: UUID,
        intersects_geometry: Any = None,
    ) -> list[GridCell]:
        """Retrieve grid cells for a given grid definition, optionally filtered by spatial constraints.

        Args:
            definition_id: The UUID of the grid definition.
            intersects_geometry: Optional geometry constraint (returns cells that intersect this geometry).
        """
        pass

    # ==========================================
    #  Search space methods
    # ==========================================

    @abstractmethod
    def create_asset(
        self,
        provider: str,
        s3_url: str | None,
        http_url: str | None,
        timestamp: datetime,
    ) -> UUID:
        """Create a new asset and return its UUID."""
        pass

    @abstractmethod
    def get_asset(self, asset_id: UUID) -> Asset | None:
        """Retrieve an asset by its UUID."""
        pass

    @abstractmethod
    def search_assets(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        provider: str | None = None,
    ) -> list[Asset]:
        """Search for assets matching the provided criteria."""
        pass

    @abstractmethod
    def link_asset_to_grid_cell(self, asset_id: UUID, cell_id: UUID) -> None:
        """Link an asset to a spatial grid cell."""
        pass

    @abstractmethod
    def link_asset_to_channel(self, asset_id: UUID, channel_id: str) -> None:
        """Link an asset to an instrument channel."""
        pass

    # ==========================================
    #  Extraction space methods
    # ==========================================

    @abstractmethod
    def create_derivative(
        self,
        cell_id: UUID,
        name: str,
        local_path: str,
        version: str,
        algorithm_name: str,
        creation_date: datetime,
    ) -> UUID:
        """Create a new derivative and return its UUID."""
        pass

    @abstractmethod
    def get_derivative(self, derivative_id: UUID) -> Derivative | None:
        """Retrieve a derivative by its UUID."""
        pass

    @abstractmethod
    def link_derivative_source(
        self,
        derivative_id: UUID,
        asset_id: UUID,
        channel_id: str,
    ) -> None:
        """Record the precise source (asset and channel) used to generate a derivative."""
        pass

    # ==========================================
    #  Satellites, Instruments & Channels methods
    # ==========================================

    @abstractmethod
    def create_satellite(
        self,
        satellite_id: str,
        satellite_name: str,
        organization: str,
    ) -> str:
        """Create a new satellite and return its ID."""
        pass

    @abstractmethod
    def get_satellite(self, satellite_id: str) -> Satellite | None:
        """Retrieve a satellite by its ID."""
        pass

    @abstractmethod
    def create_instrument(
        self,
        instrument_id: str,
        satellite_id: str,
        instrument_name: str,
        sensor_type: str,
    ) -> str:
        """Create a new instrument and return its ID."""
        pass

    @abstractmethod
    def get_instrument(self, instrument_id: str) -> Instrument | None:
        """Retrieve an instrument by its ID."""
        pass

    @abstractmethod
    def create_channel(
        self,
        channel_id: str,
        instrument_id: str,
        satellite_id: str,
        channel_name: str,
        wavelength_central: float,
        wavelength_unit: str,
    ) -> str:
        """Create a new channel and return its ID."""
        pass

    @abstractmethod
    def get_channel(self, channel_id: str) -> Channel | None:
        """Retrieve a channel by its ID."""
        pass
