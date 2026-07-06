"""MkDocs hook that copies example notebooks and config into the docs tree.

This keeps the canonical sources in the repository root under ``examples/``
while letting MkDocs (and the mknotebooks plugin) render them as pages under
``docs/examples/``. The config package is copied as well so that relative paths
inside the YAML files resolve correctly during the docs build.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def on_config(config: dict, **kwargs: object) -> dict:
    """Copy notebooks and config from ``examples/`` to ``docs/examples/``.

    Runs during config loading, before MkDocs validates the navigation and file
    tree.
    """
    docs_dir = Path(config["docs_dir"])
    repo_root = docs_dir.parent
    src_dir = repo_root / "examples"
    dst_dir = docs_dir / "examples"

    if not src_dir.is_dir():
        return config

    dst_dir.mkdir(parents=True, exist_ok=True)

    # Copy all notebooks, including step-by-step and any new ones.
    for notebook in sorted(src_dir.glob("*.ipynb")):
        shutil.copy(notebook, dst_dir / notebook.name)

    # Copy the Hydra config package so relative paths in YAML resolve.
    src_config = src_dir / "config"
    dst_config = dst_dir / "config"
    if src_config.is_dir():
        if dst_config.exists():
            shutil.rmtree(dst_config)
        shutil.copytree(src_config, dst_config)

    return config
