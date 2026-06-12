"""Example: load an AEREO extraction job from a Hydra config package.

This script shows how to compose an ``ExtractionJob`` from the Hydra config
package in this directory and run the full search → prepare → extract pipeline
with ``AereoClient``. It also demonstrates the ``target_aoi`` key and its
fallback to ``search.intersects``.

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

from aereo.backends import LocalProcessBackend
from aereo.client import AereoClient
from aereo.pipeline import ExtractionJob


DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")


def load_and_print_job(config_dir: Path) -> ExtractionJob:
    """Load a validated ``ExtractionJob`` from the config package.

    Args:
        config_dir: Directory containing the Hydra config package.

    Returns:
        A validated ``ExtractionJob`` instance.
    """
    # Optional Hydra overrides, e.g.:
    # overrides = ["patch_config=high_res", "target_aoi=/path/to/aoi.geojson"]
    overrides: list[str] | None = None

    job = ExtractionJob.load_from_config(
        config_dir,
        config_name="main_config",
        overrides=overrides,
    )

    print("\n--- Validated ExtractionJob ---")
    print(f"name: {job.name}")
    print(f"output_uri: {job.output_uri}")
    print(f"grid_config.target_grid_dist: {job.grid_config.target_grid_dist}")
    print(f"patch_config.resolution: {job.patch_config.resolution}")
    if job.search is None:
        raise ValueError("Loaded job is missing a search provider.")

    print(f"search.intersects type: {type(job.search.intersects).__name__}")
    print(f"target_aoi type: {type(job.target_aoi).__name__}")
    print(
        "effective_target_aoi is target_aoi: "
        f"{job.effective_target_aoi is job.target_aoi}"
    )

    return job


def run_pipeline(job: ExtractionJob) -> None:
    """Run search → prepare → extract for a validated job.

    Args:
        job: The validated ``ExtractionJob`` to execute.
    """
    if job.search is None:
        raise ValueError("Loaded job is missing a search provider.")

    client = AereoClient()

    # Search
    print("\n🔍 Searching...")
    search_results = client.search(job.search)
    print(f"✓ Found {len(search_results)} scenes")

    if search_results.empty:
        print("No results; skipping prepare/extract.")
        return

    # Prepare
    print("\n📦 Preparing tasks...")
    tasks = client.prepare_tasks(
        search_results=search_results,
        job=job,
        cells_per_task=50,
    )
    print(f"✓ Prepared {len(tasks)} tasks")

    # Extract
    print("\n⛏️ Extracting...")
    backend = LocalProcessBackend(max_workers=1)
    artifacts = client.execute_tasks(tasks, backend=backend)
    print(f"✓ Extracted {len(artifacts)} artifacts")


def main() -> None:
    """Entry point for the example script."""
    config_dir = Path(__file__).parent.resolve()
    print(f"Loading config package from: {config_dir}\n")

    job = load_and_print_job(config_dir)

    if DRY_RUN:
        print("\nDRY_RUN enabled: skipping search/prepare/extract.")
        return

    run_pipeline(job)


if __name__ == "__main__":
    main()
