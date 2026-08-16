# Outputs & Catalog

After an extraction you get two things: the actual raster files and a catalog
that describes where they are and how they align with the grid.

## What is written

The writer plugin controls the raster output. The default writer,
`write_geotiff`, produces one GeoTIFF per time slice and grid cell.

Common output layout:

```text
output_uri/
├── 2024/
│   └── 01/
│       └── <cell-id>_20240105T000000.tif
├── ...
└── artifacts.parquet
```

## Artifact catalog

`job.write_catalog(artifacts)` writes `artifacts.parquet`, a
`GeoDataFrame[ArtifactSchema]` with one row per artifact. Typical columns
include:

| Column | Meaning |
|---|---|
| `path` | Path or URI to the raster file. |
| `datetime` | Acquisition timestamp. |
| `cell_id` | Major TOM grid cell ID. |
| `geometry` | Artifact footprint. |
| `collection` | Source collection name. |

## Reading the catalog

```python
import geopandas as gpd

catalog = gpd.read_parquet("/tmp/aereo_demo/artifacts.parquet")
print(catalog.head())
catalog.plot(column="cell_id", legend=True)
```

## EOIDS — AerEO's output convention

EOIDS (Earth Observation Image Dataset) is AerEO's own convention for naming
and organizing extracted files. It is not an external standard; it is the
layout AerEO uses so that every output has a predictable path and metadata.

In practice:

- `output_uri` is the root of the EOIDS directory tree.
- Filenames embed keys such as `loc-`, `start-`, `end-`, `job-`, and `cell-`
  so the source scene, time range, and grid cell can be recovered from the
  path.
- `artifacts.parquet` sits at the root and is the entry point for downstream
  ML training scripts.

## Job snapshots and overwrite protection

Because filenames no longer embed the variable list, the job name identifies
the band set. To make that contract safe, every `job.execute()` run validates
the job against a `job.yaml` snapshot stored at
`{output_uri}/job-<name>/job.yaml`:

- On the first run the snapshot is written, capturing the output-defining
  configuration: grid parameters, reprojection mode, and every pipeline
  callable with its bound keyword arguments (including the collection → band
  mapping from the search provider).
- On later runs the job is compared against the snapshot. If any
  output-defining value differs, `JobConfigMismatchError` is raised **before
  any file is written**, naming the differing fields. Rename the job or
  delete the existing job directory to proceed.

Extent-only changes are intentionally allowed: `start_datetime`,
`end_datetime`, `intersects`, and `target_aoi` select *which* scenes are
produced, and the resulting files get their own `loc-`/`date-` paths, so
extending a dataset's time range or AOI does not trip the guard. Jobs built
from a Hydra YAML and identical jobs built in code compare equal, since the
snapshot is derived from the instantiated job, not the config text.

Pass `validate_snapshot=False` to `job.execute()` to bypass the check.

If you prefer a different layout, you can provide a custom writer plugin; the
writer controls how files are named under `output_uri`.

## Object-store outputs

`output_uri` can be a local path or an object-store URI such as `s3://bucket/prefix`.
Make sure the chosen writer plugin and your environment have the necessary
permissions.
