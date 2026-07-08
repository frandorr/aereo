# AerEO Config Package Example

This directory contains the example Hydra config package used by the docs and
notebooks.

```text
.
├── job_*.yaml
├── aoi/
├── grid_dist/
├── search/
├── task_builder/
├── read/
└── write/
```

See the [Configuration](https://frandorr.github.io/aereo/configuration/config-package/)
section of the docs for a full explanation of how the package works, how YAML
maps to `ExtractionJob`, and how to override values from Python.

## Quick usage

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
)
```

For a complete example, see `run_job.py` in this directory.
