# Developer Setup

AEREO uses [uv](https://docs.astral.sh/uv/) for dependency management and [Polylith](https://polylith.gitbook.io/polylith) for code organization. This guide covers cloning, syncing, and understanding the workspace layout.

## Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Git

## Clone and Install

```bash
git clone https://github.com/frandorr/aereo.git
cd aereo
uv sync --all-extras
```

The `--all-extras` flag installs optional dependencies for all plugins so you can run the full test suite.

Verify everything is wired correctly:

```bash
uv run python -c "from aereo.registry import AereoRegistry; r = AereoRegistry(); print(r.list_supported_collections())"
```

## Polylith Workspace

AEREO is organized as a Polylith workspace:

| Directory | Purpose |
|-----------|---------|
| `components/` | Reusable bricks (e.g., `aereo/grid`, `aereo/eoids`) |
| `bases/` | Entry points (e.g., `aereo/client`) |
| `projects/` | Publishable packages (e.g., `projects/aereo-core`) |
| `test/` | Mirrors the `components/` and `bases/` structure |

When adding new functionality, prefer creating or extending a component in `components/` over adding code directly to a base.

## Plugin Discovery Mechanics

`aereo` discovers plugins automatically using Python's standard `importlib.metadata` entry points mechanism:

1. Plugins declare their classes in `pyproject.toml` under `[project.entry-points."aereo.plugins"]`.
2. The `AereoRegistry` scans installed packages for these hooks dynamically upon instantiation.
3. Classes listed in entry points are stored, matching their declared `supported_collections` for fast lookup.

Collection name matching is **case-insensitive** — `"abi-l1b-radf"` and `"ABI-L1b-RadF"` both resolve to the same plugin.

To learn how to implement the code for a search provider or extractor, read [Build Your Own Plugin](../build-your-own-plugin.md).

## hatch-polylith-bricks Dev Mode

AEREO uses `hatch-polylith-bricks` to bundle bricks during an editable install. The `projects/aereo-core/pyproject.toml` already configures `build.dev-mode-dirs` so that local source edits in `components/` and `bases/` are reflected immediately without reinstalling:

```toml
[tool.hatch]
build.dev-mode-dirs = [ "../../components", "../../bases", "../../development", "." ]
```

If you are developing a plugin simultaneously with the `aereo` core framework on the same machine and notice that `uv sync` masks your local source edits, see the [Troubleshooting section in Build Your Own Plugin](../build-your-own-plugin.md#troubleshooting-local-development-alongside-aereo) for how to align `build.dev-mode-dirs` across both packages.

## Running Tests

```bash
# Full suite
uv run pytest

# Specific component
uv run pytest test/components/aereo/grid/

# With type checking
uv run basedpyright components/ bases/

# Linting
uv run ruff check .
```

## Next Steps

- Read the [Contributing Guidelines](../contributing.md) for issue reporting, conventional commits, and the pull-request process.
- Explore [Build Your Own Plugin](../build-your-own-plugin.md) to create a new plugin.
