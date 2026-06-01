"""Hamilton parallel processors for AEREO.

This shows how to run multiple processors in parallel, sequentially, or
in a merge pattern — all controlled by the pipeline config.
"""

from __future__ import annotations

from typing import Any, Sequence

import xarray as xr

# =============================================================================
# 1.  INDEPENDENT PARALLEL PROCESSORS
# =============================================================================
# When multiple processors take the SAME input and produce DIFFERENT outputs,
# Hamilton runs them in parallel automatically because there are no
# dependencies between them.


def compute_ndvi(read_scenes: xr.Dataset, red_band: str, nir_band: str) -> xr.DataArray:
    """Compute NDVI as a standalone DataArray."""
    red = read_scenes[red_band]
    nir = read_scenes[nir_band]
    return (nir - red) / (nir + red)


def compute_ndwi(read_scenes: xr.Dataset, green_band: str, swir_band: str) -> xr.DataArray:
    """Compute NDWI as a standalone DataArray."""
    green = read_scenes[green_band]
    swir = read_scenes[swir_band]
    return (green - swir) / (green + swir)


def compute_evi(read_scenes: xr.Dataset, red_band: str, nir_band: str, blue_band: str) -> xr.DataArray:
    """Compute EVI as a standalone DataArray."""
    red = read_scenes[red_band]
    nir = read_scenes[nir_band]
    blue = read_scenes[blue_band]
    return 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)


# =============================================================================
# 2.  MERGE PATTERN — combine parallel outputs back into one dataset
# =============================================================================
# After parallel processors run, you need a "merge" node that depends on
# ALL of them. Hamilton will wait for all parallel branches to finish,
# then run the merge.


def merged_indices(
    read_scenes: xr.Dataset,
    compute_ndvi: xr.DataArray,
    compute_ndwi: xr.DataArray | None = None,
    compute_evi: xr.DataArray | None = None,
) -> xr.Dataset:
    """Merge all computed indices back into the original dataset.

    This node depends on ALL parallel processors, so Hamilton:
      1. Runs compute_ndvi, compute_ndwi, compute_evi in parallel
      2. Waits for all three to finish
      3. Runs merged_indices
    """
    ds = read_scenes.copy()
    ds["ndvi"] = compute_ndvi
    if compute_ndwi is not None:
        ds["ndwi"] = compute_ndwi
    if compute_evi is not None:
        ds["evi"] = compute_evi
    return ds


# =============================================================================
# 3.  SEQUENTIAL (CHAINED) PROCESSORS
# =============================================================================
# When one processor's output is another's input, Hamilton runs them
# sequentially, respecting the dependency chain.


def mask_clouds(read_scenes: xr.Dataset, qa_band: str, cloud_bits: list[int]) -> xr.Dataset:
    """Mask cloudy pixels. Output becomes input to next processor."""
    import numpy as np

    qa = read_scenes[qa_band]
    mask = np.zeros(qa.shape, dtype=bool)
    for bit in cloud_bits:
        mask |= ((qa.values >> bit) & 1).astype(bool)

    masked = read_scenes.drop_vars(qa_band)
    for var in masked.data_vars:
        masked[var] = masked[var].where(~mask)
    return masked


def normalize_bands(mask_clouds: xr.Dataset, method: str = "minmax") -> xr.Dataset:
    """Normalize the cloud-masked dataset.

    Note: parameter name is ``mask_clouds`` — the output of the previous node.
    This creates the dependency chain: mask_clouds → normalize_bands.
    """
    normalized = mask_clouds.copy()
    for var in normalized.data_vars:
        da = normalized[var]
        if method == "minmax":
            vmin = da.min(skipna=True)
            vmax = da.max(skipna=True)
            denom = vmax - vmin
            denom = denom.where(denom != 0, 1)
            normalized[var] = (da - vmin) / denom
    return normalized


# =============================================================================
# 4.  PIPELINE COMPILER — config-driven composition
# =============================================================================
# The user provides a config that declares WHICH processors to run and HOW.
# The compiler builds the appropriate DAG structure.


from typing import Mapping


def compile_processors(
    config: Sequence[str | dict[str, Any]],
    plugin_functions: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile a processor config into Hamilton-compatible functions.

    Config formats supported::

        # Sequential (chain)
        ["mask_clouds", "normalize_bands"]

        # Parallel (independent branches that merge)
        [{"parallel": ["compute_ndvi", "compute_ndwi", "compute_evi"]}]

        # Mixed: sequential then parallel
        ["mask_clouds", {"parallel": ["compute_ndvi", "compute_ndwi"]}]
    """
    compiled: dict[str, Any] = {}
    prev_output = "read_scenes"
    merge_counter = 0

    for idx, step in enumerate(config):
        if isinstance(step, dict) and "parallel" in step:
            # Parallel branch — create wrapper for each processor
            parallel_names = []
            for proc_name in step["parallel"]:
                func = plugin_functions[proc_name]
                wrapper_name = f"parallel_{idx}_{proc_name}"

                def make_parallel(f, name, inp):
                    def wrapper(**kwargs) -> Any:
                        # Extract the input dataset from kwargs
                        ds = kwargs[inp]
                        return f(ds)
                    wrapper.__name__ = name
                    return wrapper

                compiled[wrapper_name] = make_parallel(func, wrapper_name, prev_output)
                parallel_names.append(wrapper_name)

            # Create merge node that depends on all parallel outputs
            merge_name = f"merge_{merge_counter}"
            merge_counter += 1

            def make_merge(names, inp):
                def merge(**kwargs) -> xr.Dataset:
                    ds = kwargs[inp].copy()
                    for name in names:
                        result = kwargs[name]
                        if isinstance(result, xr.DataArray):
                            ds[name.split("_")[-1]] = result
                    return ds
                merge.__name__ = merge_name
                return merge

            compiled[merge_name] = make_merge(parallel_names, prev_output)
            prev_output = merge_name

        else:
            # Sequential step
            proc_name = step if isinstance(step, str) else list(step.keys())[0]
            func = plugin_functions[proc_name]
            wrapper_name = f"step_{idx}_{proc_name}"

            def make_sequential(f, name, inp):
                def wrapper(**kwargs) -> Any:
                    ds = kwargs[inp]
                    return f(ds)
                wrapper.__name__ = name
                return wrapper

            compiled[wrapper_name] = make_sequential(func, wrapper_name, prev_output)
            prev_output = wrapper_name

    return compiled


# =============================================================================
# 5.  USAGE EXAMPLES
# =============================================================================

def example_parallel_indices():
    """Run NDVI, NDWI, and EVI in parallel from the same input."""
    from hamilton import driver

    # All three processors are discovered from plugins
    dr = driver.Builder().with_modules(
        __name__  # this module containing the processor functions
    ).build()

    # Request the MERGE node — Hamilton will:
    #   1. Run compute_ndvi, compute_ndwi, compute_evi in parallel
    #   2. Wait for all three
    #   3. Run merged_indices
    # read_scenes would come from the upstream read stage
    result = dr.execute(
        ["merged_indices"],
        inputs={
            "read_scenes": xr.Dataset(),  # placeholder
            "red_band": "B04",
            "nir_band": "B08",
            "green_band": "B03",
            "swir_band": "B11",
            "blue_band": "B02",
        },
    )
    return result["merged_indices"]


def example_sequential_chain():
    """Run mask_clouds then normalize_bands sequentially."""
    from hamilton import driver

    dr = driver.Builder().with_modules(__name__).build()

    # Request normalize_bands — Hamilton will:
    #   1. Run mask_clouds first (dependency)
    #   2. Run normalize_bands with mask_clouds output
    result = dr.execute(
        ["normalize_bands"],
        inputs={
            "read_scenes": xr.Dataset(),
            "qa_band": "SCL",
            "cloud_bits": [3, 8, 9],
            "method": "minmax",
        },
    )
    return result["normalize_bands"]


def example_mixed_pipeline():
    """Config-driven: mask clouds, then compute NDVI + NDWI in parallel."""
    from hamilton import driver

    # User config
    pipeline_config = [
        "mask_clouds",
        {"parallel": ["compute_ndvi", "compute_ndwi"]},
    ]

    # Compile to dynamic functions
    all_plugins = {
        "mask_clouds": mask_clouds,
        "compute_ndvi": compute_ndvi,
        "compute_ndwi": compute_ndwi,
    }
    compiled = compile_processors(pipeline_config, all_plugins)

    # Build driver with compiled functions
    dr = driver.Builder().with_modules(__name__).with_functions(
        list(compiled.values())
    ).build()

    # Execute — Hamilton DAG:
    #   read_scenes → mask_clouds → [compute_ndvi || compute_ndwi] → merge_0
    result = dr.execute(
        ["merge_0"],
        inputs={
            "read_scenes": xr.Dataset(),
            "qa_band": "SCL",
            "cloud_bits": [3, 8, 9],
            "red_band": "B04",
            "nir_band": "B08",
            "green_band": "B03",
            "swir_band": "B11",
        },
    )
    return result["merge_0"]


# =============================================================================
# 6.  KEY INSIGHTS
# =============================================================================
#
# - **Parallel is automatic**: When nodes have the SAME input parameter
#   (e.g., ``read_scenes``), Hamilton recognizes they are independent and
#   can run them concurrently via ParallelExecutor.
#
# - **Merge nodes create synchronization points**: The ``merged_indices``
#   function takes ALL parallel outputs as parameters, forcing Hamilton to
#   wait for all branches before continuing.
#
# - **Sequential is just dependency chaining**: ``normalize_bands`` takes
#   ``mask_clouds`` as a parameter, so Hamilton runs them in order.
#
# - **Config drives the structure**: The pipeline config declares the
#   topology (parallel vs sequential).  The compiler translates that into
#   wrapper functions whose parameter names create the dependency graph.
#
# - **No threading code needed**: Hamilton handles the parallel execution
#   via its executor.  Your processor functions stay pure and simple.
# =============================================================================
