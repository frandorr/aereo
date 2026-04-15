"""Abstract repository interfaces for spectral and spatial data access.

Defines AerSpectralRepository for satellite/instrument/channel retrieval
and AerSpatialRepository for grid cell queries with spatial filtering.
"""

from abc import ABC, abstractmethod

from aer.spatial import GridCell, GridDefinition, OverlapMode
from aer.spectral import (
    ChannelType,
    Instrument,
    Satellite,
)
from shapely.geometry.base import BaseGeometry


class AerSpectralRepository(ABC):
    """Abstract Base Class defining the Aer data access interface.

    This repository orchestrates persistence and retrieval across several
    conceptual spaces based on the Aer Entity-Relationship schema.
    """

    # ==========================================
    #  Satellites, Instruments & Channels methods
    # ==========================================

    @abstractmethod
    def get_satellite(self, acronym: str) -> Satellite:
        """Retrieve a satellite by its acronym.

        Args:
            acronym: The unique acronym identifier for the satellite.
        Returns:
            A Satellite object corresponding to the provided acronym.
        Raises:
            An exception if no satellite with the given acronym is found.
        """
        pass

    @abstractmethod
    def get_instrument(self, acronym: str) -> Instrument:
        """Retrieve an instrument by its acronym.

        Args:
            acronym (str): The unique acronym identifier for the instrument.
        Returns:
            An Instrument object corresponding to the provided acronym.
        Raises:
            An exception if no instrument with the given acronym is found.
        """
        pass

    @abstractmethod
    def get_channel(
        self,
        instrument: Instrument,
        channel_name: str | None = None,
        channel_number: int | None = None,
    ) -> ChannelType:
        """Retrieve a channel by its acronym.

        Args:
            instrument: The instrument the channel belongs to.
            channel_name: Optional name of the channel to disambiguate if multiple channels share the same acronym.
            channel_number: Optional number of the channel to disambiguate if multiple channels share the same acronym.
        Returns:
            A ChannelType object corresponding to the provided instrument acronym.
        Raises:
            An exception if no channel with the given name or position is found.
        """
        pass


class AerSpatialRepository(ABC):
    """Abstract Base Class defining the Aer spatial data access interface.

    This repository orchestrates persistence and retrieval of spatial data,
    particularly grid cells, based on the Aer Entity-Relationship schema.
    """

    @abstractmethod
    def get_grid_cells(
        self,
        grid_def: GridDefinition,
        geometry: BaseGeometry | None = None,
        overlap_mode: OverlapMode | None = None,
    ) -> list[GridCell]:
        """
        Retrieve grid cells that intersect with a given geometry
        based on a specified grid definition and overlap mode.
        Args:
            grid_def (GridDefinition): The grid definition to use.
            geometry (BaseGeometry | None): The shapely geometry to check for intersections.
                If no geometry is provided, all grid cells defined by the grid definition will be returned.
            overlap_mode (OverlapMode | None): The mode of overlap to determine how grid cells
                are selected based on their intersection with the geometry.
                Only used if geometry is provided.
        Returns:
            A list of GridCell objects that intersect with the provided geometry.
        Raises:
            An exception if no grid cells are found intersecting the geometry.
        """
        pass
