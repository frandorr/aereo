# Using Plugins

`aereo` is a plugin-based framework. Install the core package first, then add only the plugins you need for your target sensors.

---

## Curated starter kits

Pick your sensor and copy-paste:

=== "GOES ABI (public S3, no auth)"

    ```bash
    pip install aereo aereo-search-aws-goes aereo-extract-satpy
    ```

=== "Sentinel-2 (Planetary Computer)"

    ```bash
    pip install aereo aereo-search-planetary-computer aereo-extract-odc-stac
    ```

=== "MODIS / VIIRS / Sentinel-3 (NASA Earthdata)"

    ```bash
    pip install aereo aereo-search-earthaccess aereo-extract-satpy
    ```

> **Not sure which plugin you need?** Start with the GOES example — it requires no authentication.

---

## Plugin reference

| Sensor | Search Plugin | Extract Plugin | Install Command |
|--------|---------------|----------------|-----------------|
| **GOES ABI** (public S3, no auth) | `aereo-search-aws-goes` | `aereo-extract-satpy` | `pip install aereo-search-aws-goes aereo-extract-satpy` |
| **Sentinel-2** (Planetary Computer) | `aereo-search-planetary-computer` | `aereo-extract-odc-stac` | `pip install aereo-search-planetary-computer aereo-extract-odc-stac` |
| **MODIS / VIIRS** (NASA Earthdata) | `aereo-search-earthaccess` | `aereo-extract-satpy` | `pip install aereo-search-earthaccess aereo-extract-satpy` |

---

## Verify installation

```python
from aereo.registry import AerRegistry

registry = AerRegistry()
print("Supported collections:", registry.list_supported_collections())
# e.g. ['ABI-L1b-RadF', 'ABI-L2-AODF', 'MOD021KM', 'VJ202IMG', ...]
```

> [!NOTE]
> Not all plugins declare their supported collections in the registry. If your expected collection is missing, check the plugin's own documentation — it may still work when passed directly to `AerClient.search()`.

---

## Earthdata authentication (NASA sensors only)

MODIS, VIIRS, and Sentinel-3 data are hosted by NASA and require [Earthdata](https://urs.earthdata.nasa.gov/) credentials:

```bash
# Option 1: .netrc file (persistent)
echo "machine urs.earthdata.nasa.gov login YOUR_USER password YOUR_PASS" >> ~/.netrc
chmod 600 ~/.netrc

# Option 2: Environment variables (session-only)
export EARTHDATA_USERNAME=YOUR_USER
export EARTHDATA_PASSWORD=YOUR_PASS
```

---

## Next steps

- Follow the [Quick Start](quickstart.md) for a complete Search → Prepare → Extract walkthrough.
- Read the [Plugin System](plugins.md) overview to understand how discovery and routing work.
- Learn how to [Build Your Own Plugin](build-your-own-plugin.md).
