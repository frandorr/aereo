from aer.spectral import Instrument, Satellite, BandType, Band, Channel, Product


def test_custom_plugin_registration():
    """Test demonstrating how a 3rd party plugin registers new instruments and products."""

    # 1. Register entirely new Instruments and Satellites
    OLI = Instrument.register(
        "OLI",
        "https://landsat.gsfc.nasa.gov/satellites/landsat-8/spacecraft-instruments/operational-land-imager/",
    )
    LANDSAT_8 = Satellite.register("LANDSAT_8")

    # They are now first-class citizens in aer
    assert Instrument.get("OLI") is OLI
    assert Satellite.get("LANDSAT_8") is LANDSAT_8

    # 2. Define custom channels
    L8_BAND_1 = Channel(
        c_id="B1",
        instrument=OLI,
        band=Band(
            name="Coastal/Aerosol",
            band_type=BandType.VISIBLE,  # Use built-in or custom BandTypes
            central_wavelength=0.443,
            bandwidth=0.016,
        ),
        resolution=30,
    )

    # 3. Define and register a custom Product
    # Products are automatically registered in aer when they are instantiated
    LC08_PRODUCT = Product(
        name="LC08_L1TP",
        instrument=OLI,
        supported_satellites=frozenset([LANDSAT_8]),
        channels=(L8_BAND_1,),
    )

    # Verify aer correctly absorbed the new custom product
    assert Product.get("LC08_L1TP") is LC08_PRODUCT
    assert LC08_PRODUCT in Product.all()

    # Subsequent calls to register() are idempotent (they return the existing instance)
    assert Instrument.register("OLI") is OLI
