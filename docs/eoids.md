# Earth Observation Imaging Data Structure (EOIDS)

The **Earth Observation Imaging Data Structure (EOIDS)** is a standardized convention for organizing and naming large-scale remote sensing and satellite data.

It is heavily inspired by the [Brain Imaging Data Structure (BIDS)](https://bids.neuroimaging.io/), which has become the gold standard in neuroimaging for creating scalable, machine-readable, and self-documenting dataset repositories.

## Why EOIDS?

When dealing with high-frequency satellite data (like GOES, which scans every 10 minutes), traditional directory structures fail rapidly:
1. **Directory Bloat:** Dumping all `.tif` files into a single directory makes the filesystem unusable (e.g., commands like `ls` will hang when a directory contains 100,000 files).
2. **Obscure Metadata:** If metadata is only stored inside the GeoTIFF headers, downstream data loaders must open every file to filter them, which is incredibly slow over network bounds or cloud storage.
3. **Regex Hell:** Ad-hoc positional filenames (e.g., `20260101_GOES_RadF_C01.tif`) break pipelines as soon as an optional parameter is added.

EOIDS solves this by strictly enforcing **hierarchical partitioning** and **key-value pair filenames**.

---

## 1. Directory Structure (Partitioning)

EOIDS groups data geographically, temporally, and by platform. This limits the maximum number of files in any single folder, ensuring fast lookup times.

```text
dataset/
├── loc-36D61L/                         <-- 1. Location (Grid Cell)
│   ├── date-20260101/                  <-- 2. Date of Observation
│   │   ├── sat-goes_east/              <-- 3. Platform / Instrument
│   │   │   ├── loc-36D61L_start-2026...
│   │   │   ├── loc-36D61L_start-2026...
│   ├── date-20260102/
```

### Derivatives
Just like BIDS, if the data is processed or derived from the raw source (e.g., a cloud mask, a machine learning prediction, or a composite), it should be placed in a `derivatives/` folder at the root:

```text
dataset/
├── derivatives/
│   ├── cloud_mask/
│   │   ├── loc-36D61L/
│   │   │   ├── date-20260101/
│   │   │   │   ├── loc-36D61L_start-20260101T100022_desc-cloudprob.nc
```

---

## 2. Filename Specification

Filenames consist of strict `key-value` entities.
* Entities are separated by underscores (`_`).
* The key and value are separated by a hyphen (`-`).

**Format:**
`<key>-<value>_<key>-<value>.ext`

**Supported Keys:**
* `loc`: Geographic cell or region identifier (must not contain underscores).
* `start`: Start timestamp in `%Y%m%dT%H%M%S` format.
* `end`: End timestamp in `%Y%m%dT%H%M%S` format.
* `sat`: Satellite or platform identifier (e.g., `goes_east`).
* `prod`: Product type (e.g., `RadF`, `L2_AOD`).
* `band`: Specific instrument band (e.g., `C01`, `B04`).
* `res`: Spatial resolution (e.g., `1000m`).
* `desc`: Custom descriptor, typically used for derived data (e.g., `cloudmask`).

**Example:**
`loc-36D61L_start-20260101T100022_end-20260101T100932_sat-goes_east_prod-RadF_band-C01_res-1000m.tif`

**Why this is powerful:**
Any downstream script can trivially parse the metadata without opening the file:
```python
filename = "loc-36D61L_start-20260101...tif"
metadata = dict(chunk.split('-') for chunk in filename.split('.')[0].split('_'))
# {'loc': '36D61L', 'start': '20260101T100022', ...}
```

---

## 3. Usage in Code

To ensure strict compliance across all plugins, use the `build_eoids_path` function provided by the `aer.eoids` component.

```python
import datetime
from aer.eoids import build_eoids_path

# All parameters (except local_dir) are optional.
# If omitted, they simply won't appear in the directory path or filename.
path = build_eoids_path(
    local_dir="/my/dataset",
    cell_id="36D61L",
    start_time=datetime.datetime(2026, 1, 1, 10, 0, 22),
    end_time=datetime.datetime(2026, 1, 1, 10, 9, 32),
    satellite="goes_east",
    product="RadF",
    band="C01",
    resolution=1000
)

# Derived Data Example
mask_path = build_eoids_path(
    local_dir="/my/dataset",
    cell_id="36D61L",
    start_time=datetime.datetime(2026, 1, 1, 10, 0, 22),
    derivative="cloud_mask",
    desc="probability",
    suffix="nc"
)
```
