from abc import ABC, abstractmethod

from aer.spectral import (
    ChannelType,
    Instrument,
    Satellite,
)


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
            acronym: The unique acronym identifier for the instrument.
        Returns:
            An Instrument object corresponding to the provided acronym.
        Raises:
            An exception if no instrument with the given acronym is found.
        """
        pass

    @abstractmethod
    def get_channel(
        self,
        acronym: str,
        channel_name: str | None = None,
        channel_number: int | None = None,
    ) -> ChannelType:
        """Retrieve a channel by its acronym.

        Args:
            acronym: The unique acronym identifier for the instrument channel.
                channel_name: Optional name of the channel to disambiguate if multiple channels share the same acronym.
                channel_number: Optional number of the channel to disambiguate if multiple channels share the same acronym.
        Returns:
            A ChannelType object corresponding to the provided instrument acronym.
        Raises:
            An exception if no channel with the given name or position is found.
        """
        pass
