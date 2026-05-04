---
name: new-plugin
description: Create a new search and extraction plugin based on a goal and an example reference.
---

# `new-plugin` Skill

This skill automates the creation of new `aer` plugins (search and extract) for a specific data source.

## How to use this skill

When the user asks to implement a new plugin (e.g., for Sentinel-2, Landsat, or Planetary Computer), execute the following systematic process:

### 1. Understand Goal & Examples
- Read the user's goal carefully.
- Inspect the provided example website, notebook, or tutorial (using the `read_url_content` tool) to understand the necessary API calls and data fetching logic.
- Review existing reference implementations such as [aer-search-aws-goes](https://github.com/frandorr/aer-search-aws-goes) and [aer-extract-aws-goes](https://github.com/frandorr/aer-extract-aws-goes) to understand the plugin architecture, interfaces, and expected schemas.
- NOTE: Search plugins must output `GeoDataFrame[AssetSchema]`. Extract plugins must output `GeoDataFrame[ArtifactSchema]`.

### 2. Scaffold Repositories
For both the search plugin and the extract plugin, perform the following scaffolding steps:
```bash
# 1. Clone the plugin template
git clone https://github.com/frandorr/aer-plugin-template <plugin-name>

# 2. Run the template setup script
cd <plugin-name>
# The setup script typically asks for: plugin-name, author-name, and project-name
echo -e "<plugin-name>\n<author-name>\n<project-name>\n" | bash setup.sh
```

### 3. Install Specific Dependencies
Based on your knowledge of the example implementation, add required packages to each plugin:
```bash
cd <plugin-name>
uv add <dependencies...> # (e.g., pystac-client, planetary-computer, odc-stac, rioxarray)
```

### 4. Implement Search Plugin (`SearchProvider`)
Modify `components/aer/<plugin_module_name>/core.py` in the search repository.
- Inherit from `aer.interfaces.SearchProvider`.
- Override the `search` method to query the remote API (e.g., STAC catalog).
- Build and return a `GeoDataFrame` correctly cast & validated as `AssetSchema`. Required columns: `id`, `collection`, `geometry`, `start_time`, `end_time`, `href`. Additional data like the original API item dictionary can be injected for use during extraction.

### 5. Implement Extract Plugin (`Extractor`)
Modify `components/aer/<plugin_module_name>/core.py` in the extract repository.
- Inherit from `aer.interfaces.Extractor`.
- Override `prepare_for_extraction` to parse the search assets and attach extraction-specific parameters such as `resolution`.
- Override `extract` (and alternatively handle `extract_batches` if needed).
- Retrieve the data for the asset, leveraging tools like `odc.stac.load` or `rioxarray` directly with STAC signed URLs.
- Align/resample the data to the bounding box and `utm_crs` belonging to each `GridCell` overlapping the asset.
- Define a grid (by default `target_grid_d=10_000` or 10km grid limits).
- Save the processed tiles local disk as NetCDF/TIFF (`.nc`/`.tif`) files and record their absolute paths as `uri`.
- Build and return a `GeoDataFrame` correctly cast & validated as `ArtifactSchema`. Required columns: `id`, `source_ids`, `start_time`, `end_time`, `uri`, `geometry`, `collection`, `grid_cell`, `grid_dist`, `cell_geometry`, `cell_utm_crs`, `cell_utm_footprint`.

### 6. Verification
Ensure all linting errors are mitigated and the code correctly imports interfaces from `aer.interfaces`. If needed, test the entry point discoverability using `uv run poly info`.
