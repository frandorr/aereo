from aer.repository.core import AerRepository
from aer.repository.models import (
    Channel,
    Instrument,
    Satellite,
)


class InMemoryRepository(AerRepository):
    """In-memory implementation of AerRepository for testing and lightweight usage.

    Uses dictionaries to store Satellite, Instrument, and Channel entities.
    """

    def __init__(self) -> None:
        self._satellites: dict[str, Satellite] = {}
        self._instruments: dict[str, Instrument] = {}
        self._channels: dict[str, Channel] = {}

    def store_satellite(self, satellite: Satellite) -> str:
        """Store satellite and return its acronym."""
        self._satellites[satellite.acronym] = satellite
        return satellite.acronym

    def get_satellite(self, acronym: str) -> Satellite:
        """Retrieve a satellite by its acronym."""
        if acronym not in self._satellites:
            raise KeyError(f"Satellite with acronym '{acronym}' not found")
        return self._satellites[acronym]

    def store_instrument(self, instrument: Instrument) -> str:
        """Store an instrument and return its acronym."""
        self._instruments[instrument.acronym] = instrument
        return instrument.acronym

    def get_instrument(self, acronym: str) -> Instrument:
        """Retrieve an instrument by its acronym."""
        if acronym not in self._instruments:
            raise KeyError(f"Instrument with acronym '{acronym}' not found")
        return self._instruments[acronym]

    def store_channel(self, channel: Channel) -> str:
        """Store a channel and return its identifier (using central_wavelength as key)."""
        key = str(channel.central_wavelength)
        self._channels[key] = channel
        return key

    def get_channel(self, acronym: str) -> Channel:
        """Retrieve a channel by its acronym (central_wavelength)."""
        if acronym not in self._channels:
            raise KeyError(f"Channel with identifier '{acronym}' not found")
        return self._channels[acronym]
