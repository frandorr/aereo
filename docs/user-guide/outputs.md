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
│       └── <cell_id>_20240105T000000.tif
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

## EOIDS

AEREO uses the EOIDS conventions for organizing extractions. `output_uri` is
the root of an EOIDS-compatible directory tree, and the catalog is the entry
point for downstream ML training scripts.

## Object-store outputs

`output_uri` can be a local path or an object-store URI such as `s3://bucket/prefix`.
Make sure the chosen writer plugin and your environment have the necessary
permissions.
