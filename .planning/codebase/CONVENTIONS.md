# Conventions

## Code Style

- **Formatter**: `ruff format` (via pre-commit)
- **Linter**: `ruff` with `--fix` (via pre-commit)
- **Type Checking**: `mypy` in strict mode

## Type Annotations

- **Required**: All functions should have type hints
- **Tools**: Pydantic, attrs, `returns` for monadic types
- **Mypy Config**: `strict = true`, `explicit_package_bases = true`

```python
@attrs.frozen
class GridCell:
    row: str
    col: str
    bounds: Polygon
```

## attrs Usage

- Use `@attrs.frozen` for immutable domain objects
- Use `@attrs.define` for mutable objects
- Prefer `slots=True` for memory efficiency

```python
@attrs.frozen(slots=True)
class TimeRange:
    start: datetime
    end: datetime
```

## Pandera Schemas

```python
class SearchResultSchema(pa.DataFrameModel):
    product_name: Series[pa.String] = pa.Field(nullable=False)
    geometry: GeoSeries[Any] = pa.Field(nullable=True)

    class Config:
        strict = False  # Allow extra columns
        coerce = True    # Auto-cast types
```

## Error Handling

- Use `returns` monads: `Result`, `Maybe`, `Option`
- Avoid bare `try/except`; use `Result.from_value()` pattern

```python
from returns import result

def load_grid(self) -> result.Result[gpd.GeoDataFrame, GridNotFoundError]:
    ...
    return result.Success(gdf)
```

## Plugin Registration

```python
from aer.plugin import plugin

@plugin(name="my_search", category="search")
def my_search(query: SearchQuery) -> GeoDataFrame[SearchResultSchema]:
    ...
```

## Public API

- Only export symbols in `__all__`
- Keep `__init__.py` minimal — import from `core`
- Components should be loosely coupled

## Logging

```python
from structlog import get_logger
logger = get_logger()
logger.info("operation", key=value)
```

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:
1. `ruff` + `ruff-format`
2. `mypy`
3. `pyproject-fmt`
4. Basic hygiene (trailing whitespace, EOF fixer)

## Naming Patterns

| Element | Pattern | Example |
|---------|---------|---------|
| Component dir | `snake_case` | `downloader_aria2` |
| Class | `PascalCase` | `GridSpatialExtent` |
| Function | `snake_case` | `download_aria2` |
| Constant | `SCREAMING_SNAKE` | `ENV_SETTINGS` |
| Enum-like | `PascalCase` | `BandType.Visible` |
