"""Export image/png outputs from executed notebooks into docs/assets/images/.

Run this script after notebooks have been executed so their plots can be reused
as static assets in the MkDocs site.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path


NOTEBOOK_DIR = Path(__file__).parents[2] / "examples"
OUTPUT_DIR = Path(__file__).parents[1] / "assets" / "images"


def extract_images(notebook_path: Path) -> list[tuple[str, bytes]]:
    """Return (filename, png_bytes) for every image/png output in a notebook."""
    with notebook_path.open("r", encoding="utf-8") as f:
        nb = json.load(f)

    base_name = notebook_path.stem
    images: list[tuple[str, bytes]] = []

    for cell_index, cell in enumerate(nb.get("cells", [])):
        cell_id = cell.get("id") or f"cell-{cell_index}"
        # Sanitise cell id for use as a filename fragment.
        cell_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(cell_id))

        for output in cell.get("outputs", []):
            data = output.get("data", {})
            if "image/png" not in data:
                continue

            b64 = data["image/png"]
            if isinstance(b64, list):
                b64 = "".join(b64)
            png_bytes = base64.b64decode(b64)
            filename = f"{base_name}-{cell_id}.png"
            images.append((filename, png_bytes))

    return images


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    exported = 0
    for notebook_path in sorted(NOTEBOOK_DIR.glob("*.ipynb")):
        images = extract_images(notebook_path)
        if not images:
            continue

        print(f"{notebook_path.name}: {len(images)} image(s)")
        for filename, png_bytes in images:
            out_path = OUTPUT_DIR / filename
            out_path.write_bytes(png_bytes)
            print(f"  → {out_path}")
            exported += 1

    print(f"\nExported {exported} image(s) to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
