# Contributing to AEREO

Thank you for your interest in contributing to AEREO! This document provides guidelines for reporting issues, setting up your development environment, and submitting changes.

## Table of Contents

- [Reporting Issues](#reporting-issues)
- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Pull Request Process](#pull-request-process)
- [Conventional Commits](#conventional-commits)
- [Code Style](#code-style)

## Reporting Issues

Before opening a new issue, please search existing issues to avoid duplicates.

When reporting bugs, include:
- A clear, descriptive title
- Steps to reproduce the issue
- Expected vs. actual behavior
- Your Python version (`python --version`)
- Relevant environment details (OS, plugin versions)
- Full error messages and tracebacks

For feature requests, describe the use case and the problem you're trying to solve.

## Development Setup

AEREO uses [uv](https://docs.astral.sh/uv/) for dependency management and [Polylith](https://polylith.gitbook.io/polylith) for code organization.

### Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Git

### Clone and Install

```bash
git clone https://github.com/frandorr/aereo.git
cd aereo
uv sync --all-extras
```

The `--all-extras` flag installs optional dependencies for all plugins so you can run the full test suite.

### Polylith Workspace

AEREO is organized as a Polylith workspace:

- `components/` — reusable bricks (e.g., `aereo/data`, `aereo/grid`)
- `bases/` — entry points (e.g., `aereo/client`)
- `projects/` — publishable packages (e.g., `projects/aereo-core`)
- `test/` — mirrors the `components/` and `bases/` structure

When adding new functionality, prefer creating or extending a component in `components/` over adding code directly to a base.

## Running Tests

### All Tests

```bash
uv run pytest
```

### Specific Test Directory

```bash
uv run pytest test/components/aereo/grid
```

### With Type Checking

```bash
uv run basedpyright components/ bases/
```

### Linting

```bash
uv run ruff check .
```

### Slow Tests

Some tests are marked as slow or integration tests. To skip them:

```bash
uv run pytest -m "not slow and not integration"
```

To run integration tests (requires credentials):

```bash
RUN_INTEGRATION_TESTS=1 uv run pytest -m integration
```

## Pull Request Process

1. **Fork and branch** — Create a feature branch from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes** — Write code, tests, and documentation.

3. **Run checks locally** — Ensure tests, type checks, and linting pass:
   ```bash
   uv run pytest
   uv run ruff check .
   uv run basedpyright components/ bases/
   ```

4. **Commit** — Use [Conventional Commits](#conventional-commits).

5. **Push and open a PR** — Fill out the PR template and link any related issues.

6. **Review** — Maintainers will review and may request changes.

## Conventional Commits

We use [Conventional Commits](https://www.conventionalcommits.org/) to automate changelogs and versioning.

Format:
```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

Common types:
- `feat` — new feature
- `fix` — bug fix
- `docs` — documentation only
- `style` — formatting, missing semicolons, etc.
- `refactor` — code change that neither fixes a bug nor adds a feature
- `test` — adding or correcting tests
- `chore` — maintenance tasks, dependency updates

Examples:
```
feat(grid): add support for custom CRS in grid alignment
fix(extract): handle missing bands in satpy reader
docs(readme): update installation instructions
```

## Code Style

- **Formatter**: Ruff (replaces Black)
- **Linter**: Ruff (replaces flake8, isort, pydocstyle)
- **Type checker**: basedpyright
- **Line length**: 88 characters

Configuration is in `pyproject.toml`.

---

## Questions?

Feel free to open a [Discussion](https://github.com/frandorr/aereo/discussions) or reach out in an existing issue.
