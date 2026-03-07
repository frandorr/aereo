# aer-downloader-aria2

This package provides an `aria2c`-backed high-performance, parallel data downloader plugin for the [aer framework](https://github.com/frandorr/aer).

It resolves and delegates downloads locally to the `aria2c` process using `--input-file`.

## Requirements

-   `aer-core >= 1.0.0`
-   The `aria2c` executable must be installed on your system and available in your `PATH` (e.g., `apt install aria2`, `brew install aria2`).

## Usage

This plugin integrates seamlessly as a `@plugin` within the `aer` capability graph. When installed, `aer` discovers it automatically via entry points.

```bash
pip install aer-downloader-aria2
```

```python
from aer.bootstrap import bootstrap
from aer.plugin import plugin_registry

# Load all installed plugins
bootstrap()

# The parallel downloader is now registered!
downloader = plugin_registry.get("aria2")
results = downloader(requests, max_concurrent=10)
```
