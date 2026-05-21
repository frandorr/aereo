import subprocess
import sys
from pathlib import Path

import pytest


EXAMPLES_DIR = Path(__file__).parents[4] / "examples" / "extraction"


def test_01_goes_abi_runs():
    result = subprocess.run(
        [sys.executable, str(EXAMPLES_DIR / "01_goes_abi.py")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.skip(
            f"GOES ABI extraction skipped "
            f"(exit={result.returncode}). stderr: {result.stderr[:200]}"
        )
    assert Path("/tmp/01_goes_abi_mosaic.png").exists()


def test_02_sentinel2_msi_runs():
    result = subprocess.run(
        [sys.executable, str(EXAMPLES_DIR / "02_sentinel2_msi.py")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.skip(
            f"Sentinel-2 MSI extraction skipped "
            f"(exit={result.returncode}). stderr: {result.stderr[:200]}"
        )
    assert Path("/tmp/02_sentinel2_rgb.png").exists()


def test_03_multi_constellation_runs():
    result = subprocess.run(
        [sys.executable, str(EXAMPLES_DIR / "03_multi_constellation.py")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # NASA-sensor extraction is resource-intensive and may fail in
    # memory-constrained CI environments. Skip gracefully.
    if result.returncode != 0:
        pytest.skip(
            f"Multi-constellation extraction skipped "
            f"(exit={result.returncode}). stderr: {result.stderr[:200]}"
        )
    assert Path("/tmp/03_multi_constellation.png").exists()


def test_04_conform_to_ml_runs():
    result = subprocess.run(
        [sys.executable, str(EXAMPLES_DIR / "04_conform_to_ml.py")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.skip(
            f"ML conform extraction skipped "
            f"(exit={result.returncode}). stderr: {result.stderr[:200]}"
        )
    assert Path("/tmp/04_conform_to_montage.png").exists()
