# Built-in plugins

`aereo.builtins` ships with ready-to-use plugins for common satellite data
workflows. These cover search, read, reproject, process, and write stages.

## Search providers

::: aereo.builtins.search
    options:
      members:
        - SearchSTAC
        - SearchEarthaccess

## Readers

::: aereo.builtins.read
    options:
      members:
        - ReadODCSTAC

## Reprojectors

::: aereo.builtins.reproject
    options:
      members:
        - ReprojectODC

## Processors

::: aereo.builtins.processor
    options:
      members:
        - SelectBands
        - QAMask
        - NDVI
        - Normalize
        - Composite

## Writers

::: aereo.builtins.write
    options:
      members:
        - WriteGeoTIFF

::: aereo.builtins.batch_write
    options:
      members:
        - BatchWriteGeoTIFF
