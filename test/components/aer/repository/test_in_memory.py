"""Tests for InMemoryRepository."""

import pytest

from aer.repository import Channel, InMemoryRepository, Instrument, Satellite


class TestInMemoryRepository:
    """Test cases for InMemoryRepository."""

    @pytest.fixture
    def repo(self):
        """Create a fresh InMemoryRepository for each test."""
        return InMemoryRepository()

    def test_store_and_get_satellite(self, repo):
        """Test storing and retrieving a satellite."""
        instrument = Instrument(
            acronym="MSI",
            channels=[
                Channel(
                    central_wavelength=0.5,
                    bandwidth=0.1,
                    unit="um",
                    resolution_m=20.0,
                )
            ],
        )
        satellite = Satellite(acronym="SENTINEL-2", payload=[instrument])

        returned_acronym = repo.store_satellite(satellite)

        assert returned_acronym == "SENTINEL-2"
        retrieved = repo.get_satellite("SENTINEL-2")
        assert retrieved.acronym == satellite.acronym
        assert retrieved.payload == satellite.payload

    def test_get_satellite_not_found(self, repo):
        """Test that KeyError is raised for non-existent satellite."""
        with pytest.raises(
            KeyError, match="Satellite with acronym 'NONEXISTENT' not found"
        ):
            repo.get_satellite("NONEXISTENT")

    def test_store_and_get_instrument(self, repo):
        """Test storing and retrieving an instrument."""
        channel = Channel(
            central_wavelength=11.0,
            bandwidth=1.0,
            unit="um",
            resolution_m=1000.0,
        )
        instrument = Instrument(acronym="AIRS", channels=[channel])

        returned_acronym = repo.store_instrument(instrument)

        assert returned_acronym == "AIRS"
        retrieved = repo.get_instrument("AIRS")
        assert retrieved.acronym == instrument.acronym
        assert retrieved.channels == instrument.channels

    def test_get_instrument_not_found(self, repo):
        """Test that KeyError is raised for non-existent instrument."""
        with pytest.raises(
            KeyError, match="Instrument with acronym 'NONEXISTENT' not found"
        ):
            repo.get_instrument("NONEXISTENT")

    def test_store_and_get_channel(self, repo):
        """Test storing and retrieving a channel."""
        channel = Channel(
            central_wavelength=0.65,
            bandwidth=0.05,
            unit="um",
            resolution_m=10.0,
        )

        returned_key = repo.store_channel(channel)

        assert returned_key == "0.65"
        retrieved = repo.get_channel("0.65")
        assert retrieved.central_wavelength == channel.central_wavelength
        assert retrieved.bandwidth == channel.bandwidth
        assert retrieved.unit == channel.unit
        assert retrieved.resolution_m == channel.resolution_m

    def test_get_channel_not_found(self, repo):
        """Test that KeyError is raised for non-existent channel."""
        with pytest.raises(KeyError, match="Channel with identifier '99.0' not found"):
            repo.get_channel("99.0")
