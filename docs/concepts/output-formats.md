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

EOIDS groups data by job, geography, and date. This limits the maximum number of files in any single folder, ensuring fast lookup times.

```text
dataset/
├── job-sentinel2_b04_sample/           <-- 1. ExtractionJob name
│   ├── loc-36D61L/                     <-- 2. Geographic cell
│   │   ├── date-20260101/              <-- 3. Date of Observation
│   │   │   ├── job.json                <-- 4. Job metadata sidecar
│   │   │   ├── collection-S2-L2A_loc-36D61L_start-2026...
│   │   │   ├── collection-S2-L2A_loc-36D61L_start-2026...
│   ├── date-20260102/
```

Because `collection` and `variable` are declared inside the `ExtractionJob.search` configuration, they are encoded directly in the filename rather than as extra subdirectories. This keeps the hierarchy flat and avoids redundant nesting.

### Derivatives

Just like BIDS, if the data is processed or derived from the raw source (e.g., a cloud mask, a machine learning prediction, or a composite), it should be placed in a `derivatives/` folder at the root:

```text
dataset/
├── derivatives/
│   ├── cloud_mask/
│   │   ├── job-sentinel2_b04_sample/
│   │   │   ├── loc-36D61L/
│   │   │   │   ├── date-20260101/
│   │   │   │   │   ├── collection-ABI-L1b-RadF_loc-36D61L_start-20260101T100022_variable-cloud_prob_res-1000m_job-goes_c01.nc
```

### `job.json` sidecar

Every job directory may contain a `job.json` file that stores the job name and optional metadata. It is written automatically on the first call to `build_eoids_path` and enables external inspection or BIDS-style inheritance:

```json
{
  "job": "sentinel2_b04_sample"
}
```

### One ExtractionJob = One Artifact File

An `ExtractionJob` produces **exactly one artifact file per grid cell**. All variables extracted for that cell are stored as separate **bands** inside that single file — they are never split into multiple files.

This means:

* A job that extracts `B04`, `B03`, and `B02` from Sentinel-2 yields a single 3-band GeoTIFF per cell.
* The `variable` segment in the EOIDS filename (e.g. `variable-B04+B03+B02`) describes the **set of bands contained in the file**, not a request to write separate files.

If an extractor truly needs one file per variable, it must define a separate `ExtractionJob` for each.

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
* `job`: ExtractionJob name (e.g., `sentinel2_b04_sample`).
* `collection`: Collection identifier (e.g., `ABI-L1b-RadF`). Auto-derived from the search results.
* `variable`: Specific variable or band (e.g., `C01`, `B04`). Auto-derived from the dataset.
* `res`: Spatial resolution (e.g., `1000m`).

**Example:**
`collection-ABI-L1b-RadF_loc-36D61L_start-20260101T100022_end-20260101T100932_variable-C01_res-1000m_job-goes_c01.tif`

### `+` concatenation for multi-collection / multi-variable jobs

When a job extracts more than one collection or variable, the values are joined by `+` in the filename:

```text
collection-IMG202+IMG203_loc-1U10L_start-20260101T100000_variable-I04+I05_res-375m_job-viirs_geo.tif
```

This preserves the exact extraction configuration in a single filename while remaining machine-parseable.

**Why this is powerful:**
Any downstream script can trivially parse the metadata without opening the file:

```python
from aereo.eoids import parse_eoids_filename

metadata = parse_eoids_filename(
    "collection-ABI-L1b-RadF_loc-36D61L_start-20260101T100022_"
    "end-20260101T100932_variable-C01_res-1000m_job-goes_c01.tif"
)
# {'loc': '36D61L', 'start': '20260101T100022', 'end': '20260101T100932',
#  'job': 'goes_c01', 'collection': 'ABI-L1b-RadF',
#  'variable': 'C01', 'res': '1000m'}
```

---

## 3. Usage in Code

To ensure strict compliance across all plugins, use the `build_eoids_path` function provided by the `aereo.eoids` component.

```python
import datetime
from aereo.eoids import build_eoids_path

path = build_eoids_path(
    local_dir="/my/dataset",
    job_name="goes_c01",
    resolution=1000.0,
    collections=["ABI-L1b-RadF"],
    variables=["C01"],
    cell_id="36D61L",
    start_time=datetime.datetime(2026, 1, 1, 10, 0, 22),
    end_time=datetime.datetime(2026, 1, 1, 10, 9, 32),
)

# Derived Data Example
mask_path = build_eoids_path(
    local_dir="/my/dataset",
    job_name="goes_c01",
    resolution=1000.0,
    collections=["ABI-L1b-RadF"],
    variables=["cloud_prob"],
    cell_id="36D61L",
    start_time=datetime.datetime(2026, 1, 1, 10, 0, 22),
    derivative="cloud_mask",
    suffix="nc",
)
```

When using the pipeline, writers take the job name from `task.job.name` automatically.

---

## 4. majortom Integration Note

While `job.json` provides on-disk metadata for external inspection, the **authoritative source** for collection/variable mapping in a pipeline context is the `ArtifactSchema` inside the `majortom` geodataframe. The sidecar file is intended for recovery, sharing, and debugging; runtime decisions should always use the in-memory schema attached to the active dataframe.
