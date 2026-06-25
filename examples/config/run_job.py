"""Example: load an AEREO extraction job from a Hydra config package.

This script shows how to compose an ``ExtractionJob`` from the Hydra config
package in this directory and run the full search → prepare → extract pipeline
with ``ExtractionJob`` methods. It also demonstrates the ``target_aoi`` key.

Usage:
    cd examples/config
    uv run python run_job.py

The default config performs a real STAC search against the Planetary Computer
endpoint. Set ``DRY_RUN=true`` to skip network calls and only validate the
loaded configuration:

    DRY_RUN=true uv run python run_job.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import hydra
from aereo.executors import LocalExecutor
from aereo.interfaces import SearchProvider, TaskBuilder
from aereo.pipeline import ExtractionJob
from hydra import compose, initialize_config_dir


DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")


def load_job_and_plugins(
    config_dir: Path,
    config_name: str = "job_sentinel2",
) -> tuple[ExtractionJob, SearchProvider, TaskBuilder]:
    """Load a validated ``ExtractionJob`` plus search/task-builder plugins.

    Args:
        config_dir: Directory containing the Hydra config package.
        config_name: Name of the root config file (without ``.yaml``).

    Returns:
        A tuple of ``(job, search_provider, task_builder)``.
    """
    with initialize_config_dir(version_base=None, config_dir=str(config_dir)):
        cfg = compose(config_name=config_name)
        instantiated = hydra.utils.instantiate(cfg, _convert_="all")

    if not isinstance(instantiated, dict):
        raise ValueError(
            f"Expected Hydra to produce a dict, got {type(instantiated).__name__}"
        )

    job_kwargs: dict[str, Any] = dict(instantiated)
    search_provider = job_kwargs.pop("search", None)
    task_builder = job_kwargs.pop("task_builder", None)

    if search_provider is None:
        raise ValueError("Loaded config is missing a search provider.")
    if task_builder is None:
        raise ValueError("Loaded config is missing a task builder.")

    job = ExtractionJob(**job_kwargs)
    return job, search_provider, task_builder


def run_pipeline(
    job: ExtractionJob,
    search_provider: SearchProvider,
    task_builder: TaskBuilder,
) -> None:
    """Run search → prepare → extract for a validated job.

    Args:
        job: The validated ``ExtractionJob`` to execute.
        search_provider: Search provider to use.
        task_builder: Task builder to use.
    """
    # Search
    print("\n🔍 Searching...")
    search_results = job.search(search_provider)
    print(f"✓ Found {len(search_results)} scenes")

    if search_results.empty:
        print("No results; skipping prepare/extract.")
        return

    # Prepare
    print("\n📦 Preparing tasks...")
    tasks = job.build_tasks(search_results, task_builder)
    print(f"✓ Prepared {len(tasks)} tasks")

    # Extract
    print("\n⛏️ Extracting...")
    executor = LocalExecutor(workers=1)
    artifacts = job.execute(tasks, executor=executor)
    print(f"✓ Extracted {len(artifacts)} artifacts")


def main() -> None:
    """Entry point for the example script."""
    config_dir = Path(__file__).parent.resolve()
    print(f"Loading config package from: {config_dir}\n")

    job, search_provider, task_builder = load_job_and_plugins(config_dir)

    print("--- Validated ExtractionJob ---")
    print(f"name: {job.name}")
    print(f"output_uri: {job.output_uri}")
    print(f"grid_config.target_grid_dist: {job.grid_config.target_grid_dist}")
    print(f"patch_config.resolution: {job.patch_config.resolution}")
    print(f"target_aoi type: {type(job.target_aoi).__name__}")
    print(
        "effective_target_aoi is target_aoi: "
        f"{job.effective_target_aoi is job.target_aoi}"
    )

    if DRY_RUN:
        print("\nDRY_RUN enabled: skipping search/prepare/extract.")
        return

    run_pipeline(job, search_provider, task_builder)


if __name__ == "__main__":
    main()
