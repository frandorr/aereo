# Quick Start

Get from zero to your first extracted satellite image in under 5 minutes.

## Install

=== "pip"

    ```bash
    pip install aer-eo
    ```

=== "uv"

    ```bash
    uv add aer-eo
    ```

## Your First Search

```python
from datetime import datetime, timezone
from aer.client import AerClient
from aer.interfaces import AerProfile

client = AerClient()

results = client.search(
    profiles=[
        AerProfile(
            name="goes_c07",
            resolution=2000,
            collections={"ABI-L1b-RadF": ["C07"]},
            search_params={"satellite": "GOES-19"},
        )
    ],
    start_datetime=datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 1, 15, 10, tzinfo=timezone.utc),
    intersects=aoi_geometry,
)
```

## Your First Extraction

```python
from aer.client import AerClient

client = AerClient()
tasks = client.prepare_for_extraction(results, profiles=profiles, uri="out")
artifacts = client.extract_batches(tasks)
```

## Next Steps

- Read the [Architecture Overview](pipeline-architecture.md)
- Explore [Available Plugins](plugins.md)
- Learn to [Build Your Own Plugin](build-your-own-plugin.md)
