"""Tests for the aereo-extract CLI scaffold."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aereo.cli.extract import app
from typer.testing import CliRunner


runner = CliRunner()


def test_init_docker_scaffold(tmp_path: Any) -> None:
    """init-docker emits Dockerfile, compose file, and starter package."""
    result = runner.invoke(
        app,
        ["my-extract", "--output", str(tmp_path), "--package", "my_reader"],
    )
    assert result.exit_code == 0

    project_dir = Path(tmp_path) / "my-extract"
    assert (project_dir / "Dockerfile").exists()
    assert (project_dir / "docker-compose.yml").exists()
    assert (project_dir / "invoke_local.py").exists()
    assert (project_dir / "README.md").exists()
    assert (project_dir / "my_reader" / "__init__.py").exists()
    assert (project_dir / "my_reader" / "custom_reader.py").exists()

    dockerfile = (project_dir / "Dockerfile").read_text()
    assert "aereo-extract-base" in dockerfile
    assert "my_reader" in dockerfile


def test_init_docker_refuses_existing_directory(tmp_path: Any) -> None:
    """init-docker exits when the target directory already exists."""
    (tmp_path / "my-extract").mkdir()
    result = runner.invoke(
        app,
        ["my-extract", "--output", str(tmp_path)],
    )
    assert result.exit_code == 1
