# aer Plugin System

`aer.spectral` uses an **extensible open registry** model. This allows third-party developers (e.g., `aer_landsat` or `aer_sentinel2`) to define entirely custom satellite, sensor, and product taxonomies that seamlessly interact with `aer` pipelines, without requiring pull requests to the core `aer` repository.

## How it Works

The core concepts—`Instrument`, `Satellite`, `BandType`, and `Product`—are not strict `Enums`. Instead, they are immutable frozen dataclasses backed by class-level registries.

When you dynamically call `.register()` on any of these bases, it:
1. Instantiates your new element.
2. Adds it to the global `aer` namespace.
3. Automatically maps it for runtime validators, tests, and CLI tools via `.get()` and `.all()`.

## Writing a Plugin

To create a new `aer` extension, simply author a new pip-installable Python package or internal module.

### Best Practice: The Registry API

Because plugins are extending the namespace dynamically, static type-checkers (like `mypy`) do not know what `Instrument.OLI` is at compile time.

**The typed API contract is:**
Always map the return value of `.register()` to a variable. The variable contains the fully-typed `Instrument`, `Satellite`, or `BandType` instance, making it fully transparent to your IDE.

### Complete Example: Extrapolating `aer` for Landsat 8

Here is a tested, fully functional example demonstrating how you would build a custom `aer` taxonomy in a downstream script or package.

```python
from aer.spectral import Instrument, Satellite, BandType, Band, Channel, Product

def register_landsat_plugin():
    # 1. Register entirely new Instruments and Satellites.
    # We assign the outputs to variables for type safety later!
    OLI = Instrument.register("OLI", "https://landsat.gsfc.nasa.gov/satellites/landsat-8/spacecraft-instruments/operational-land-imager/")
    LANDSAT_8 = Satellite.register("LANDSAT_8")

    # 2. Define custom channels using standard aer interfaces
    L8_BAND_1 = Channel(
        c_id="B1",
        instrument=OLI,        # Notice we use the typed 'OLI' variable
        band=Band(
            name="Coastal/Aerosol",
            band_type=BandType.VISIBLE,  # Core types work perfectly with custom instruments
            central_wavelength=0.443,
            bandwidth=0.016,
        ),
        resolution=30,
    )

    # 3. Define the data product
    # Important: Product classes immediately, automatically register themselves
    # into Product.all() and Product.get() upon initialization.
    LC08_PRODUCT = Product(
        name="LC08_L1TP",
        instrument=OLI,
        supported_satellites=frozenset([LANDSAT_8]),
        channels=(L8_BAND_1,)
    )

    return LC08_PRODUCT

# In your pipeline script:
my_custom_product = register_landsat_plugin()

# aer's core is now permanently aware of your custom products!
assert Instrument.get("OLI").name == "OLI"
assert Satellite.get("LANDSAT_8").name == "LANDSAT_8"
assert Product.get("LC08_L1TP") is my_custom_product

# You can now feed `LC08_L1TP` to native aer methods (like aer.search_earthaccess) safely!
```

## The API Surface

| Class | Registration | Query | Iterator |
|---|---|---|---|
| `Instrument` | `Instrument.register("NAME", url="...")` | `Instrument.get("NAME")` | `Instrument.all()` |
| `Satellite` | `Satellite.register("NAME", url="...")` | `Satellite.get("NAME")` | `Satellite.all()` |
| `BandType` | `BandType.register("Name")` | `BandType.get("Name")` | `BandType.all()` |
| `Product` | `Product(name="P", ...)` | `Product.get("P")` | `Product.all()` |

*Note: Registrations are **idempotent**. If your plugin script calls `Satellite.register("LANDSAT_8")` multiple times, it simply returns the identical, already-registered instance.*

## Search Plugins & Discovery

While `spectral` plugins are usually loaded via explicit module imports, `SearchMethod` plugins are discovered automatically via **Python Entry Points**.

### The Bootstrap Mechanism

To initialize the registry with all installed search plugins, call `bootstrap()`:

```python
from aer.bootstrap import bootstrap
bootstrap()
```

This triggers `aer.plugins` to scan for entry points in the `aer.plugins.search` group and load the associated modules.

### Plugin Discovery (Crucial for Dev)

Plugins are declared in the `[project.entry-points]` section of your `pyproject.toml`.

```toml
[project.entry-points."aer.plugins.search"]
earthaccess = "aer.search_earthaccess.core:SEARCH_EARTHACCESS"
```

> [!IMPORTANT]
> **Workspace Discovery Root**: In a Polylith development environment, `importlib.metadata` reads discovery metadata from the package that is currently installed in the environment (the root `pyproject.toml` when using `uv sync` at the workspace root).
>
> If you add a new plugin to a `projects/` sub-package but **do not** add it to the root `pyproject.toml`, it will be missing from the registry during development, leading to `KeyError: "Search method '...' is not registered."`. Always mirror your plugin entry points in the root configuration during active development.
