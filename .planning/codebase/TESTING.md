# Testing

## Framework

- **pytest** (>=9.0.2)
- **Run via**: `uv run pytest`

## Structure

Tests mirror the component structure:
```
test/
├── bases/aer/download_api/test_core.py
├── components/aer/search/test_core.py
├── components/aer/spatial/test_core.py
└── integration/
    ├── test_plugins.py
    └── test_core_only.py
```

## Running Tests

```bash
# All tests
uv run pytest

# Specific component
uv run pytest test/components/aer/spectral/

# Integration tests only
uv run pytest test/integration/

# Skip slow tests
uv run pytest -m "not slow"
```

## Test Markers

Defined in `pyproject.toml`:

| Marker | Purpose |
|---------|---------|
| `slow` | Long-running tests (deselect with `-m "not slow"`) |
| `integration` | Cross-component integration tests |

## Mocking

- Standard `unittest.mock` for external services
- Mock S3, HTTP requests, file I/O

## Coverage

- `.pytest_cache/` tracks test runs
- Coverage reports generated via pytest-cov (if added)

## Integration Tests

Located in `test/integration/`:
- `test_plugins.py` — Plugin discovery and registration
- `test_core_only.py` — Core functionality without plugins

## Test Utilities

- Use `attrs.evolve()` for creating test variants
- Fixtures in `conftest.py` (if added)

## Test Data

- Grid parquet files: `components/aer/spatial/grid_*.parquet`
- Use real data samples for integration tests
