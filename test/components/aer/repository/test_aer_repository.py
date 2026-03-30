"""Tests for AerLocalSpectralRepository using real WMO OSCAR data."""

import pytest

from aer.repository import AerLocalSpectralRepository


@pytest.fixture
def repo():
    """Provide a fresh AerLocalSpectralRepository instance."""
    return AerLocalSpectralRepository()


class TestAerLocalSpectralRepository:
    """Test AerLocalSpectralRepository with real WMO OSCAR data."""

    def test_get_satellite_aqua(self, repo):
        """Test retrieving Aqua satellite from CSV data."""
        satellite = repo.get_satellite("Aqua")

        assert satellite.acronym == "Aqua"
        assert satellite.orbit == "SunSync"
        assert satellite.altitude_km == 705.0
        assert satellite.status == "Operational"
        # Aqua has many instruments, just check payload is a list
        assert isinstance(satellite.payload, list)

    def test_get_satellite_not_found(self, repo):
        """Test that KeyError is raised for non-existent satellite."""
        with pytest.raises(
            KeyError, match="Satellite with acronym 'NONEXISTENT' not found"
        ):
            repo.get_satellite("NONEXISTENT")

    def test_get_instrument_modis(self, repo):
        """Test retrieving MODIS instrument from JSON data."""
        instrument = repo.get_instrument("MODIS")

        assert instrument.acronym == "MODIS"
        # MODIS should have many channels
        assert len(instrument.channels) > 0
        # Check first channel has expected attributes
        channel = instrument.channels[0]
        assert hasattr(channel, "channel_name")
        assert hasattr(channel, "instrument_acronym")

    def test_get_instrument_viirs(self, repo):
        """Test retrieving VIIRS instrument from JSON data."""
        instrument = repo.get_instrument("VIIRS")

        assert instrument.acronym == "VIIRS"
        assert len(instrument.channels) > 0

    def test_get_instrument_not_found(self, repo):
        """Test that KeyError is raised for non-existent instrument."""
        with pytest.raises(
            KeyError, match="Instrument with acronym 'NONEXISTENT' not found"
        ):
            repo.get_instrument("NONEXISTENT")

    def test_get_channel_by_name_modis(self, repo):
        """Test retrieving a MODIS channel by name."""
        # MODIS has channel names like "B01", "B02", etc.
        channel = repo.get_channel("MODIS", channel_name="B01")

        assert channel.channel_name == "B01"
        assert channel.instrument_acronym == "MODIS"
        assert hasattr(channel, "central_wavelength")

    def test_get_channel_by_number_viirs(self, repo):
        """Test retrieving a VIIRS channel by number."""
        # Get first channel
        channel = repo.get_channel("VIIRS", channel_number=1)

        assert channel.instrument_acronym == "VIIRS"
        assert hasattr(channel, "channel_name")

    def test_get_channel_not_found_by_name(self, repo):
        """Test that KeyError is raised for non-existent channel name."""
        with pytest.raises(
            KeyError, match="Channel name 'NonExistent' not found in instrument 'MODIS'"
        ):
            repo.get_channel("MODIS", channel_name="NonExistent")

    def test_get_channel_not_found_by_number(self, repo):
        """Test that KeyError is raised for out-of-range channel number."""
        with pytest.raises(
            KeyError, match="Channel number 999 is out of range for instrument 'MODIS'"
        ):
            repo.get_channel("MODIS", channel_number=999)

    def test_get_channel_requires_name_or_number(self, repo):
        """Test that ValueError is raised when neither name nor number provided."""
        with pytest.raises(
            ValueError, match="Either channel_name or channel_number must be provided"
        ):
            repo.get_channel("MODIS")

    def test_get_channel_rejects_both_name_and_number(self, repo):
        """Test that ValueError is raised when both name and number provided."""
        with pytest.raises(
            ValueError,
            match="Only one of channel_name or channel_number should be provided",
        ):
            repo.get_channel("MODIS", channel_name="test", channel_number=1)
