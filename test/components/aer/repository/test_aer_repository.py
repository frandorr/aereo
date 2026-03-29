"""Abstract tests for AerRepository implementations.

Use this to create tests for any AerRepository implementation (database-backed, etc.)
by subclassing and providing a `repo` fixture.

Example:
    class TestMyRepository(TestAerRepositoryBase):
        @pytest.fixture
        def repo(self):
            return MyRepository()
"""

import pytest

from aer.repository import Channel, Instrument, Satellite


@pytest.mark.skip(reason="Abstract base class - subclass and provide repo fixture")
class TestAerRepositoryBase:
    """Abstract test cases for AerRepository implementations.

    Subclasses must provide a `repo` fixture that returns a fresh
    AerRepository instance.
    """

    @pytest.fixture
    def repo(self):
        """Override in subclass to provide concrete repository."""
        raise NotImplementedError("Subclass must provide `repo` fixture")

    def test_store_and_get_satellite(self, repo):
        """Test storing and retrieving a satellite."""
        instrument = Instrument(
            satellite_acronym="SENTINEL-2",
            acronym="MSI",
            channels=[
                Channel(
                    instrument_acronym="MSI",
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

    def test_get_satellite_not_found(self, repo):
        """Test that KeyError is raised for non-existent satellite."""
        with pytest.raises(
            KeyError, match="Satellite with acronym 'NONEXISTENT' not found"
        ):
            repo.get_satellite("NONEXISTENT")

    def test_store_and_get_instrument(self, repo):
        """Test storing and retrieving an instrument after storing its satellite."""
        satellite = Satellite(acronym="AQUA", payload=[])
        repo.store_satellite(satellite)

        channel = Channel(
            instrument_acronym="AIRS",
            central_wavelength=11.0,
            bandwidth=1.0,
            unit="um",
            resolution_m=1000.0,
        )
        instrument = Instrument(
            satellite_acronym="AQUA", acronym="AIRS", channels=[channel]
        )

        returned_acronym = repo.store_instrument(instrument)

        assert returned_acronym == "AIRS"
        retrieved = repo.get_instrument("AIRS")
        assert retrieved.acronym == instrument.acronym
        assert retrieved.satellite_acronym == instrument.satellite_acronym

    def test_store_instrument_missing_satellite(self, repo):
        """Test that KeyError is raised when storing instrument without satellite."""
        instrument = Instrument(
            satellite_acronym="NONEXISTENT",
            acronym="TEST",
            channels=[],
        )

        with pytest.raises(KeyError, match="Satellite 'NONEXISTENT' not found"):
            repo.store_instrument(instrument)

    def test_get_instrument_not_found(self, repo):
        """Test that KeyError is raised for non-existent instrument."""
        with pytest.raises(
            KeyError, match="Instrument with acronym 'NONEXISTENT' not found"
        ):
            repo.get_instrument("NONEXISTENT")

    def test_store_and_get_channel(self, repo):
        """Test storing and retrieving a channel after storing its instrument and satellite."""
        satellite = Satellite(acronym="TERRA", payload=[])
        repo.store_satellite(satellite)

        instrument = Instrument(
            satellite_acronym="TERRA",
            acronym="MODIS",
            channels=[],
        )
        repo.store_instrument(instrument)

        channel = Channel(
            instrument_acronym="MODIS",
            central_wavelength=0.65,
            bandwidth=0.05,
            unit="um",
            resolution_m=10.0,
        )

        returned_key = repo.store_channel(channel)

        assert returned_key == "0.65"
        retrieved = repo.get_channel("0.65")
        assert retrieved.central_wavelength == channel.central_wavelength
        assert retrieved.instrument_acronym == channel.instrument_acronym

    def test_store_channel_missing_instrument(self, repo):
        """Test that KeyError is raised when storing channel without instrument."""
        channel = Channel(
            instrument_acronym="NONEXISTENT",
            central_wavelength=0.65,
            bandwidth=0.05,
            unit="um",
            resolution_m=10.0,
        )

        with pytest.raises(KeyError, match="Instrument 'NONEXISTENT' not found"):
            repo.store_channel(channel)

    def test_get_channel_not_found(self, repo):
        """Test that KeyError is raised for non-existent channel."""
        with pytest.raises(KeyError, match="Channel with identifier '99.0' not found"):
            repo.get_channel("99.0")
