# Contributing

AerEO is a Polylith monorepo managed with `uv` and `uv poly`.

## Development setup

```bash
git clone https://github.com/frandorr/aereo.git
cd aereo
uv sync
```

## Run tests

```bash
uv run pytest test/ -v --tb=short
```

## Lint and type check

```bash
uv run ruff check .
uv run basedpyright
```

## Build the docs

```bash
uv sync --extra docs
uv run mkdocs serve
```

The docs include the example notebooks under `examples/`. They are copied into
`docs/examples/` by `docs/hooks/copy_notebooks.py` and rendered with
`mknotebooks`. Notebooks are **not** executed during the build; the rendered
pages rely on the outputs already saved in the notebooks.

## Commit style

This project uses [Conventional Commits](https://www.conventionalcommits.org/).
Examples:

```text
feat(search): add Earthaccess search provider
docs(tutorial): add Sentinel-3 NDVI notebook
fix(grid): handle empty intersection results
```

## Code style

- Google-style docstrings.
- Use `| None` instead of `Optional`.
- Type hints on all public functions.
- Do not use `assert` for runtime input validation; raise explicit exceptions.

## Getting help

- [GitHub Issues](https://github.com/frandorr/aereo/issues)
- [GitHub Discussions](https://github.com/frandorr/aereo/discussions)
