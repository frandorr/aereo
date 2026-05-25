# aereoeo

`aereo` is a modular, high-performance capability-graph framework for downloading, parsing, and transforming Earth Observation sensor data.

This `aereo` package includes the base registries, spatial transforms, dependency grids, and foundational typing rules meant to be extended by third-party Python plugin components.

## Features

- **Strict Validations:** Uses `pandera` and `geopandas` for 100% rigorous parsing of geo-features.
- **Capability Graph Engine:** Automatically infers plugin IO shapes dynamically.
- **Lazy Discovery Engine:** Finds and eagerly caches dynamic instrument components.
- **SatPy/PyResample Wrappers:** Seamless grid abstractions across `utm`, `proj`.

For building capabilities and plugins on top of `aereo`, see our official Plugin Developer Guide on the repository docs!
