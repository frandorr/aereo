"""Example: Hamilton integration with AEREO's plugin system.

This module shows how AEREO could adopt Hamilton to compose extraction
pipelines while retaining its entry-point plugin discovery.  The key question
"how can Hamilton add processors without knowing them?" is answered by
Hamilton's ``with_modules()`` API — it introspects arbitrary Python modules
and automatically adds every function as a DAG node.
"""

from __future__ import annotations

import importlib
import importlib.metadata
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# 1.  What a processor plugin looks like today (imperative class)
# ---------------------------------------------------------------------------

from aereo.interfaces import Processor, AereoDataset, ExtractionTask
from aereo.registry import AereoRegistry
from pandera.typing.geopandas import GeoDataFrame
try:
    from hamilton import driver
except ImportError:
    driver = None  # type: ignore


class NDVI(Processor):
    """Post-reproject processor that computes NDVI."""

    supported_collections = ("*",)
    stage = "post_reproject"

    def process(self, ds: AereoDataset, params: Mapping[str, Any]) -> AereoDataset:
        nir_band = params["ndvi_nir_band"]
        red_band = params["ndvi_red_band"]
        nir = ds[nir_band]
        red = ds[red_band]
        ndvi = (nir - red) / (nir + red)
        result = ds.drop_vars([nir_band, red_band])
        result["ndvi"] = ndvi
        return result


# ---------------------------------------------------------------------------
# 2.  Hamilton version — pure functions in a module
# ---------------------------------------------------------------------------
# Hamilton builds a DAG by inspecting *functions* inside *modules*.  The
# function name becomes the node name; parameters become upstream
# dependencies.  No central registry needs to know the names ahead of time.

from typing import Mapping


def ndvi(
    ds: AereoDataset,
    ndvi_nir_band: str,
    ndvi_red_band: str,
) -> AereoDataset:
    """Compute NDVI = (NIR - Red) / (NIR + Red)."""
    nir = ds[ndvi_nir_band]
    red = ds[ndvi_red_band]
    ndvi = (nir - red) / (nir + red)
    result = ds.drop_vars([ndvi_nir_band, ndvi_red_band])
    result["ndvi"] = ndvi
    return result


def select_bands(ds: AereoDataset, bands: list[str]) -> AereoDataset:
    """Keep only requested data variables."""
    return ds[bands]


def qa_mask(
    ds: AereoDataset,
    qa_band: str,
    qa_mask_bits: list[int],
) -> AereoDataset:
    """Mask pixels where any QA bit is set."""
    import numpy as np

    qa = ds[qa_band]
    mask = np.zeros(qa.shape, dtype=bool)
    for bit in qa_mask_bits:
        mask |= ((qa.values >> bit) & 1).astype(bool)
    masked = ds.drop_vars(qa_band)
    for var in masked.data_vars:
        masked[var] = masked[var].where(~mask)
    return masked


# ---------------------------------------------------------------------------
# 3.  Dynamic discovery — the answer to "without knowing them"
# ---------------------------------------------------------------------------
# Hamilton's ``Builder.with_modules(*modules)`` accepts *any* modules.
# AEREO already has entry-point discovery; we just swap class loading for
# module loading.


def discover_hamilton_modules(group: str = "aereo.hamilton_processors") -> list[Any]:
    """Discover and import every module registered under *group*.

    Returns a list of loaded module objects suitable for
    ``driver.Builder().with_modules(*...)``.
    """
    modules = []
    for ep in importlib.metadata.entry_points(group=group):
        try:
            # Entry point value is a dotted module path, e.g.
            # "my_plugin.hamilton_nodes"
            mod = importlib.import_module(ep.value)
            modules.append(mod)
        except Exception as exc:
            print(f"Failed to load Hamilton module {ep.name}: {exc}")
    return modules


# ---------------------------------------------------------------------------
# 4.  Wiring it together inside AEREO's TaskRunner
# ---------------------------------------------------------------------------


def run_pipeline_with_hamilton(
    task: "ExtractionTask",
    registry: "AereoRegistry",
) -> "GeoDataFrame":
    """Execute a task using Hamilton to compose the processing DAG.

    The runner no longer calls ``processor.process()`` imperatively.
    Instead it:

    1. Loads the reader, reprojector, writer via the existing registry.
    2. Discovers *all* Hamilton processor modules installed on the system.
    3. Builds a Hamilton driver that wires read → process → reproject → write.
    4. Executes the DAG; Hamilton figures out which nodes to run.
    """
    if driver is None:
        raise ImportError("hamilton is required for this runner")

    if task.pipeline is None:
        raise ValueError("Task must have a pipeline configured")

    # --- AEREO-style plugin instantiation (unchanged) ----------------------
    read_plugin = task.pipeline.read.plugin
    reproject_plugin = task.pipeline.reproject.plugin
    write_plugin = task.pipeline.write.plugin
    if read_plugin is None or reproject_plugin is None or write_plugin is None:
        raise ValueError("Pipeline is missing a required stage plugin")
    reader = registry.get("reader", read_plugin)
    reprojector = registry.get("reprojector", reproject_plugin)
    writer = registry.get("writer", write_plugin)

    # --- Hamilton dynamic module loading (the magic) -----------------------
    processor_modules = discover_hamilton_modules()

    # Build a driver that knows about:
    #   • built-in pipeline primitives (read, reproject, write)
    #   • every function exported by every discovered processor plugin
    dr = (
        driver.Builder()
        .with_modules(
            # You can mix built-in modules and dynamically discovered ones
            *processor_modules,
        )
        .build()
    )

    # Map AEREO task config to Hamilton inputs
    inputs = {
        "task": task,
        "reader": reader,
        "reprojector": reprojector,
        "writer": writer,
        # Parameters flow straight through as named inputs
        **task.pipeline.read.params,
        **task.pipeline.reproject.params,
        **task.pipeline.write.params,
    }
    # Add processor params; Hamilton will only consume the keys that
    # match actual function parameters in the discovered modules.
    for proc in task.pipeline.process:
        inputs.update(proc.params)

    # Execute — Hamilton resolves the DAG automatically
    results = dr.execute(["final_artifacts"], inputs=inputs)
    return results["final_artifacts"]


# ---------------------------------------------------------------------------
# 5.  What the built-in module (read / reproject / write) looks like
# ---------------------------------------------------------------------------
# This is the "glue" module that AEREO itself ships.  It defines the stable
# nodes that processor plugins depend on or feed into.


def raw_dataset(task, reader) -> AereoDataset:
    """Read assets into an AereoDataset."""
    return reader.read(task, task.pipeline.read.params)


def reprojected_dataset(raw_dataset, reprojector, geobox) -> AereoDataset:
    """Reproject to target grid."""
    return reprojector.reproject(raw_dataset, geobox, {})


def final_artifacts(reprojected_dataset, task, writer) -> "GeoDataFrame":
    """Write each grid cell and collect artifacts."""
    # (Simplified — real impl would loop over cells)
    cell = task.grid_cells[0]
    return writer.write(reprojected_dataset, task, cell, {})


# ---------------------------------------------------------------------------
# 6.  How a 3rd-party plugin package declares itself
# ---------------------------------------------------------------------------
# In ``pyproject.toml``:
#
#   [project.entry-points."aereo.hamilton_processors"]
#   my_ndwi = "my_plugin.nodes"
#
# The module ``my_plugin.nodes`` just contains plain functions:
#
#   def ndwi(ds, green_band: str, swir_band: str) -> AereoDataset:
#       ...
#
# Hamilton sees ``ndwi`` as a node.  If the user's pipeline config does NOT
# request ``ndwi`` as a final output, Hamilton skips it.  If it DOES,
# Hamilton runs it (and any upstream dependencies) automatically.
#
# Because ``with_modules`` loads the module by import-path, AEREO never
# needs to import the function by name or maintain a registry of names.
# ---------------------------------------------------------------------------
