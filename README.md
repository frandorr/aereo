# Python Polylith Template with `uv`

A minimal template repository for Python projects using the [Polylith architecture](https://davidvujic.github.io/python-polylith-docs/setup/), powered by `uv` for lightning-fast dependency management, and `perk` for git hooks.

## Philosophy

This repository is designed to be a clean, modern starting point for teams looking to use:
* **Polylith** for a modular, monorepo-friendly and maintainable architecture.
* **uv** for exceptionally fast and reliable Python packaging and virtual environments.
* **perk** for lightweight, tool-managed git hooks instead of traditional pre-commit.

---

## Getting Started

### Prerequisites

To get started, you don't need anything pre-installed if you use the provided setup script. The setup script will automatically install `uv` (if not present) and `perk`. If you prefer to set things up manually, ensure you have `uv` installed.

### Automatic Setup

Run the setup script:

```bash
./setup.sh
```

The script will automatically do the heavy lifting:
1. Prompt you for a simple project name.
2. Update the `name` in `pyproject.toml` and the `namespace` in `workspace.toml` automatically.
3. Install `uv` (if it's not already installed on your system).
4. Add `polylith-cli` as a development dependency and run `uv sync` to set up your virtual environment.
5. Install `perk` globally via `uv tool install perk`.

---

## Project Structure

Polylith organizes your codebase into interchangeable blocks, prioritizing composability:

* `components/` – Reusable functional blocks (the core logic). They are the lego bricks of your application.
* `bases/` – Application entry points (e.g., an API router, a CLI task, or an AWS Lambda handler), acting as the outer shell exposing features.
* `projects/` – Deployable artifacts that compose one or more bases and components. They do not contain logic directly, just assembling the pieces.

For more detailed information about Polylith and how its concepts apply in Python, check out the [official Python Polylith Documentation](https://davidvujic.github.io/python-polylith-docs/setup/).

### Creating Blocks

You can create components, bases, and projects effortlessly using the Polylith CLI (which is available via `uv run` once synced):

```bash
# Create a new component
uv run poly create component --name my_component

# Create a new base
uv run poly create base --name my_base

# Create a new project
uv run poly create project --name my_project
```

### Inspecting the Workspace

Polylith shines at giving you an overview of your monorepo. Check your projects, bases, and components with:

```bash
uv run poly info
```

---

## Development Workflow

1. **Install dependencies:**  
   If you need to manually sync your environment or add third-party dependencies, use `uv`:
   ```bash
   uv sync
   uv add requests
   uv add --group dev pytest
   ```

2. **Run tests:**  
   You can run your tests across the entire workspace easily using `pytest`. The template enables tests globally across components:
   ```bash
   uv run pytest
   ```

3. **Hooks (perk):**  
   We use `perk` for streamlined commit checks. The setup script installs it globally via `uv tool install perk`. You can use it to configure git workflows without heavy external dependencies.

---

## License

MIT