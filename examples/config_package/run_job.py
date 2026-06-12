"""Example: load an AEREO extraction job from a Hydra config package.

This script shows how to compose an ``ExtractionJob`` from the Hydra config
package in this directory and run the full search → prepare → extract pipeline
with ``AereoClient``. It also demonstrates the ``target_aoi`` key and its
fallback to ``search.intersects``.

Usage:
    cd examples/config_package
    uv run python run_job.py

The default config performs a real STAC search against the Planetary Computer
endpoint. Set ``DRY_RUN=true`` to skip network calls and only validate the
loaded configuration:

    DRY_RUN=true uv run python run_job.py
"""

from __future__ import annotations

import os
from pathlib import Path

import hydra
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from aereo.backends import LocalProcessBackend
from aereo.client import AereoClient
from aereo.pipeline import ExtractionJob


DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")


def load_job(
    config_dir: str | Path, overrides: list[str] | None = None
) -> ExtractionJob:
    """Load and validate an ExtractionJob from a Hydra config package.

    Args:
        config_dir: Directory containing the Hydra config package.
        overrides: Optional Hydra command-line style overrides.

    Returns:
        A validated ``ExtractionJob`` instance.
    """
    with initialize_config_dir(version_base=None, config_dir=str(config_dir)):
        cfg = compose(config_name="main_config", overrides=overrides or [])
        print("--- Composed OmegaConf ---")
        print(OmegaConf.to_yaml(cfg))

        instantiated = hydra.utils.instantiate(cfg, _convert_="all")
        job = ExtractionJob.model_validate(instantiated)

    print("\n--- Validated ExtractionJob ---")
    print(f"output_uri: {job.output_uri}")
    print(f"grid_config.target_grid_dist: {job.grid_config.target_grid_dist}")
    print(f"patch_config.resolution: {job.patch_config.resolution}")
    print(f"search.intersects type: {type(job.search.intersects).__name__}")
    print(f"target_aoi type: {type(job.target_aoi).__name__}")
    print(
        f"effective_target_aoi is target_aoi: {job.effective_target_aoi is job.target_aoi}"
    )

    return job


def run_pipeline(job: ExtractionJob) -> None:
    """Run search → prepare → extract for a validated job.

    Args:
        job: The validated ``ExtractionJob`` to execute.
    """
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
        extract=job.extract,
        grid_config=job.grid_config,
        patch_config=job.patch_config,
        output_uri=job.output_uri,
        target_aoi=job.effective_target_aoi,
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

    # Example override: switch to a different patch config or AOI path
    # overrides = ["patch_config=high_res", f"target_aoi={config_dir / 'aoi/sample.geojson'}"]
    overrides: list[str] | None = None

    job = load_job(config_dir, overrides=overrides)

    if DRY_RUN:
        print("\nDRY_RUN enabled: skipping search/prepare/extract.")
        return

    run_pipeline(job)


if __name__ == "__main__":
    main()
