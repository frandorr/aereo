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
├── loc-36D61L/                         <-- 1. Geographic cell
│   ├── date-20260101/                  <-- 2. Date of Observation
│   │   ├── profile-goes_c01/           <-- 3. Profile name
│   │   │   ├── profile.json            <-- 4. Profile metadata sidecar
│   │   │   ├── loc-36D61L_start-2026...
│   │   │   ├── loc-36D61L_start-2026...
│   ├── date-20260102/
```

Because `collection` and `variable` are declared inside the `AereoProfile`, they are encoded directly in the filename rather than as extra subdirectories. This keeps the hierarchy flat and avoids redundant nesting.

### Derivatives
Just like BIDS, if the data is processed or derived from the raw source (e.g., a cloud mask, a machine learning prediction, or a composite), it should be placed in a `derivatives/` folder at the root:

```text
dataset/
├── derivatives/
│   ├── cloud_mask/
│   │   ├── loc-36D61L/
│   │   │   ├── date-20260101/
│   │   │   │   ├── profile-goes_c01/
│   │   │   │   │   ├── loc-36D61L_start-20260101T100022_desc-cloudprob.nc
```

### `profile.json` sidecar

Every profile directory may contain a `profile.json` file that stores the full serialized `AereoProfile` metadata (resolution, padding, plugin hints, search parameters, etc.). It is written automatically on the first call to `build_eoids_path` and enables external inspection or BIDS-style inheritance:

```json
{
  "name": "goes_c01",
  "resolution": 1000.0,
  "collections": {
    "ABI-L1b-RadF": ["C01"]
  }
}
```

The `downloader` callable is intentionally excluded from serialization because it cannot be represented in JSON.

### One Profile = One Artifact File

An `AereoProfile` produces **exactly one artifact file per grid cell**.  All
variables declared in `profile.collections` are stored as separate **bands**
inside that single file — they are never split into multiple files.

This means:

* A profile with `collections = {"sentinel-2-l2a": ["B04", "B03", "B02"]}`
  yields a single 3-band GeoTIFF per cell.
* The `variable` segment in the EOIDS filename (e.g.
  `variable-B04+B03+B02`) describes the **set of bands contained in the
  file**, not a request to write separate files.

If an extractor truly needs one file per variable, it must define a
separate `AereoProfile` for each.

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
* `profile`: Profile name (e.g., `goes_c01`).
* `collection`: Collection identifier (e.g., `ABI-L1b-RadF`). Auto-derived from the profile.
* `variable`: Specific variable or band (e.g., `C01`, `B04`). Auto-derived from the profile.
* `res`: Spatial resolution (e.g., `1000m`).
* `desc`: Custom descriptor, typically used for derived data (e.g., `cloudmask`).

**Example:**
`loc-36D61L_start-20260101T100022_end-20260101T100932_profile-goes_c01_collection-ABI-L1b-RadF_variable-C01_res-1000m.tif`

### `+` concatenation for multi-collection / multi-variable profiles

When a profile declares more than one collection or variable, the values are joined by `+` in the filename:

```text
loc-1U10L_start-20260101T100000_profile-viirs_geo_collection-IMG202+IMG203_variable-I04+I05_res-375m.tif
```

This preserves the exact profile configuration in a single filename while remaining machine-parseable.

**Why this is powerful:**
Any downstream script can trivially parse the metadata without opening the file:
```python
filename = "loc-36D61L_start-20260101...tif"
metadata = dict(chunk.split('-') for chunk in filename.split('.')[0].split('_'))
# {'loc': '36D61L', 'start': '20260101T100022', ...}
```

---

## 3. Usage in Code

To ensure strict compliance across all plugins, use the `build_eoids_path` function provided by the `aereo.eoids` component.

```python
import datetime
from aereo.eoids import build_eoids_path
from aereo.interfaces import AereoProfile

profile = AereoProfile(
    name="goes_c01",
    collections={"ABI-L1b-RadF": ["C01"]},
)

# collection, variable, and resolution are derived automatically from the
# AereoProfile. All other parameters (except local_dir and profile) are optional.
# If omitted, they simply won't appear in the directory path or filename.
path = build_eoids_path(
    local_dir="/my/dataset",
    profile=profile,
    cell_id="36D61L",
    start_time=datetime.datetime(2026, 1, 1, 10, 0, 22),
    end_time=datetime.datetime(2026, 1, 1, 10, 9, 32),
)

# Derived Data Example
mask_path = build_eoids_path(
    local_dir="/my/dataset",
    profile=profile,
    cell_id="36D61L",
    start_time=datetime.datetime(2026, 1, 1, 10, 0, 22),
    derivative="cloud_mask",
    desc="probability",
    suffix="nc"
)
```

---

## 4. majortom Integration Note

While `profile.json` provides on-disk metadata for external inspection, the **authoritative source** for collection/variable mapping in a pipeline context is the `ArtifactSchema` inside the `majortom` geodataframe. The sidecar file is intended for recovery, sharing, and debugging; runtime decisions should always use the in-memory schema attached to the active dataframe.
