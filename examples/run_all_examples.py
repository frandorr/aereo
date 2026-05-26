#!/usr/bin/env python3
"""Run all aereo examples and verify outputs contain valid data."""

import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import rasterio


EXAMPLES = [
    {
        "name": "01_minimal_goes",
        "script": Path(__file__).parent / "extraction" / "01_minimal_goes.py",
        "output_dir": Path("/tmp/01_minimal_goes_out"),
    },
    {
        "name": "02_goes_mosaic_plot",
        "script": Path(__file__).parent / "extraction" / "02_goes_mosaic_plot.py",
        "output_dir": Path("/tmp/02_goes_mosaic_plot_extraction"),
    },
    {
        "name": "03_sentinel2_msi",
        "script": Path(__file__).parent / "extraction" / "03_sentinel2_msi.py",
        "output_dir": Path("/tmp/03_sentinel2_msi_extraction"),
    },
    {
        "name": "04_multi_constellation",
        "script": Path(__file__).parent / "extraction" / "04_multi_constellation.py",
        "output_dir": Path("/tmp/04_multi_constellation_extraction"),
    },
    {
        "name": "05_conform_to_ml",
        "script": Path(__file__).parent / "extraction" / "05_conform_to_ml.py",
        "output_dir": Path("/tmp/05_conform_to_ml_extraction"),
    },
    {
        "name": "06_geotessera",
        "script": Path(__file__).parent / "extraction" / "06_geotessera.py",
        "output_dir": Path(
            "/root/repos/aereo/examples/extraction/09_geotessera_extraction_output"
        ),
    },
]


def check_tifs_valid(output_dir: Path) -> dict[str, Any]:
    """Return {path: {'valid_ratio': float, 'shape': tuple, 'bands': int, 'dtype': str}}.

    valid_ratio = proportion of pixels that are finite and > 0 (or != 0 for signed).
    """
    results = {}
    tifs = sorted(output_dir.rglob("*.tif"))
    if not tifs:
        return results
    for tif in tifs:
        with rasterio.open(tif) as src:
            arr = src.read()
            # For float data, check finite and not nodata
            # For integer data, check not nodata
            if np.issubdtype(arr.dtype, np.floating):
                valid = np.isfinite(arr) & (arr != 0)
            else:
                valid = arr != 0
            valid_ratio = valid.sum() / valid.size
            results[str(tif.relative_to(output_dir))] = {
                "valid_ratio": float(valid_ratio),
                "shape": arr.shape,
                "bands": src.count,
                "dtype": str(arr.dtype),
                "crs": str(src.crs),
            }
    return results


def run_example(example: dict) -> dict:
    """Run a single example script and return verification results."""
    name = example["name"]
    script = example["script"]
    output_dir = example["output_dir"]

    # Clean previous output
    if output_dir.exists():
        import shutil

        shutil.rmtree(output_dir)

    print(f"\n{'=' * 60}")
    print(f"Running {name} ...")
    print(f"{'=' * 60}")

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=600,  # 10 min per example
    )

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    if result.returncode != 0:
        return {
            "name": name,
            "success": False,
            "error": f"Exit code {result.returncode}",
            "stderr": result.stderr,
        }

    # Verify outputs
    tif_results = check_tifs_valid(output_dir)
    empty_files = [p for p, info in tif_results.items() if info["valid_ratio"] == 0]
    low_valid = [p for p, info in tif_results.items() if info["valid_ratio"] < 0.01]

    return {
        "name": name,
        "success": True,
        "tif_count": len(tif_results),
        "empty_files": empty_files,
        "low_valid": low_valid,
        "tif_details": tif_results,
    }


def main() -> int:
    all_passed = True
    summary = []

    for example in EXAMPLES:
        result = run_example(example)
        summary.append(result)

        if not result["success"]:
            print(f"\n❌ {result['name']}: FAILED — {result['error']}")
            all_passed = False
            continue

        if result["empty_files"]:
            print(f"\n❌ {result['name']}: Completely empty file(s) (all zero/NaN):")
            for f in result["empty_files"]:
                print(f"   - {f}")
            all_passed = False
        elif result["low_valid"]:
            print(
                f"\n⚠️  {result['name']}: Very low valid pixel ratio (<1%) in {len(result['low_valid'])} file(s):"
            )
            for f in result["low_valid"]:
                info = result["tif_details"][f]
                print(f"   - {f}: valid_ratio={info['valid_ratio']:.2%}")
            # Don't fail for low valid - conform_to with padding can legitimately have lots of padding
        else:
            print(
                f"\n✅ {result['name']}: PASSED — {result['tif_count']} GeoTIFF(s) with valid data"
            )

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    for r in summary:
        if not r["success"]:
            status = "❌ FAIL"
        elif r.get("empty_files"):
            status = "❌ FAIL (empty)"
        else:
            status = "✅ PASS"
        print(f"{status}: {r['name']}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
