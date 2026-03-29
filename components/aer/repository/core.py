from abc import ABC, abstractmethod

from aer.repository.models import (
    Channel,
    Instrument,
    Satellite,
)


class AerRepository(ABC):
    """Abstract Base Class defining the Aer data access interface.

    This repository orchestrates persistence and retrieval across several
    conceptual spaces based on the Aer Entity-Relationship schema.
    """

    # ==========================================
    #  Satellites, Instruments & Channels methods
    # ==========================================

    @abstractmethod
    def store_satellite(self, satellite: Satellite) -> str:
        """Store satellite and return its ID."""
        pass

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
    def store_instrument(self, instrument: Instrument) -> str:
        """Store an instrument and return its ID."""
        pass

    @abstractmethod
    def get_instrument(self, acronym: str) -> Instrument:
        """Retrieve an instrument by its acronym.

        Args:
            acronym: The unique acronym identifier for the instrument.
        Returns:
            An Instrument object corresponding to the provided acronym.
        Raises:
            An exception if no instrument with the given acronym is found.
        """
        pass

    @abstractmethod
    def store_channel(self, channel: Channel) -> str:
        """Store a channel and return its ID."""
        pass

    @abstractmethod
    def get_channel(self, acronym: str) -> Channel:
        """Retrieve a channel by its acronym.

        Args:
            acronym: The unique acronym identifier for the channel.
        Returns:
            A Channel object corresponding to the provided acronym.
        Raises:
            An exception if no channel with the given acronym is found.
        """
        pass
