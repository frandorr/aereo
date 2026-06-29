# Built-in plugins

`aereo.builtins` ships with ready-to-use functions for common satellite data
workflows. These cover search, read, reproject, process, and write stages.
Each function is decorated with Pydantic validation, so invalid arguments raise
clear errors before any network or disk I/O runs.

## Search providers

::: aereo.builtins.search
    options:
      members:
        - search_stac
        - search_earthaccess

## Readers

::: aereo.builtins.read
    options:
      members:
        - read_odc_stac

## Reprojectors

::: aereo.builtins.reproject
    options:
      members:
        - reproject_odc

## Processors

::: aereo.builtins.processor
    options:
      members:
        - select_bands
        - qa_mask
        - ndvi
        - normalize
        - composite

## Writers

::: aereo.builtins.write
    options:
      members:
        - write_geotiff
