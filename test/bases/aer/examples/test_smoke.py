import subprocess
import sys
from pathlib import Path


EXAMPLES_DIR = Path(__file__).parents[4] / "examples" / "extraction"


def test_01_goes_abi_runs():
    result = subprocess.run(
        [sys.executable, str(EXAMPLES_DIR / "01_goes_abi.py")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert Path("/tmp/01_goes_abi_mosaic.png").exists()
