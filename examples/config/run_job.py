"""Example: load an AerEO extraction job from a Hydra config package.

This script shows how to compose an ``ExtractionJob`` from the Hydra config
package in this directory and run the full search → build-tasks → extract
pipeline with ``ExtractionJob`` methods. Search and task-builder plugins are
loaded separately because they are runtime concerns, not part of the job
model.

Usage:
    cd examples
    uv run python config/run_job.py

The default config performs a real STAC search against the Earth Search
endpoint. Set ``DRY_RUN=true`` to skip network calls and only validate the
loaded configuration:

    DRY_RUN=true uv run python config/run_job.py
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from aereo.executors import LocalExecutor
from aereo.interfaces import SearchProvider, TaskBuilder
from aereo.pipeline import ExtractionJob, load_plugin


DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")


def load_job(config_dir: Path, config_name: str = "job_sentinel2") -> ExtractionJob:
    """Load a validated ``ExtractionJob`` from the Hydra config package.

    Args:
        config_dir: Directory containing the Hydra config package.
        config_name: Name of the root config file (without ``.yaml``).

    Returns:
        A validated ``ExtractionJob`` instance.
    """
    return ExtractionJob.load_from_config(config_dir, config_name=config_name)


def load_plugins(
    config_dir: Path,
    search_name: str = "sentinel2_pc",
    task_builder_name: str = "grouped",
) -> tuple[SearchProvider, TaskBuilder]:
    """Load search provider and task builder plugins from the config package.

    Args:
        config_dir: Directory containing the Hydra config package.
        search_name: Name of the search provider config file.
        task_builder_name: Name of the task builder config file.

    Returns:
        A tuple of ``(search_provider, task_builder)``.
    """
    search_provider = load_plugin(config_dir, "search", search_name)
    task_builder = load_plugin(config_dir, "task_builder", task_builder_name)
    return search_provider, task_builder


def run_pipeline(
    job: ExtractionJob,
    search_provider: SearchProvider,
    task_builder: TaskBuilder,
) -> None:
    """Run search → build-tasks → extract for a validated job.

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
        print("No results; skipping build-tasks/extract.")
        return

    # Build tasks
    print("\n📦 Building tasks...")
    tasks = job.build_tasks(search_results, task_builder)
    print(f"✓ Built {len(tasks)} tasks")

    # Extract
    print("\n⛏️ Extracting...")
    executor = LocalExecutor(workers=1)
    artifacts = job.execute(tasks, executor=executor)
    print(f"✓ Extracted {len(artifacts)} artifacts")


def main() -> None:
    """Entry point for the example script."""
    parser = argparse.ArgumentParser(
        description="Run an AerEO extraction from a Hydra config package."
    )
    parser.add_argument(
        "--config-name",
        default="job_sentinel2",
        help="Root job config name (without .yaml).",
    )
    parser.add_argument(
        "--search",
        default="sentinel2_pc",
        help="Search provider config name (without .yaml).",
    )
    parser.add_argument(
        "--task-builder",
        default="grouped",
        help="Task builder config name (without .yaml).",
    )
    args = parser.parse_args()

    config_dir = Path(__file__).parent.resolve()
    print(f"Loading config package from: {config_dir}\n")

    job = load_job(config_dir, config_name=args.config_name)
    search_provider, task_builder = load_plugins(
        config_dir,
        search_name=args.search,
        task_builder_name=args.task_builder,
    )

    print("--- Validated ExtractionJob ---")
    print(f"name: {job.name}")
    print(f"output_uri: {job.output_uri}")
    print(f"grid_dist: {job.grid_dist}")
    print(f"target_aoi type: {type(job.target_aoi).__name__}")
    print(
        "effective_target_aoi is target_aoi: "
        f"{job.effective_target_aoi is job.target_aoi}"
    )

    if DRY_RUN:
        print("\nDRY_RUN enabled: skipping search/build-tasks/extract.")
        return

    run_pipeline(job, search_provider, task_builder)


if __name__ == "__main__":
    main()
