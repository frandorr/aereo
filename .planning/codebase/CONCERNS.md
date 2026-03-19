# Concerns

## Technical Debt

### Type Checking Disabled
- `no-untyped-def` and `no-untyped-call` are disabled in mypy config (see `pyproject.toml:86-88`)
- **Action**: Gradually add type annotations to untyped functions

### ClassVar Registries
- `Instrument`, `Satellite`, `BandType`, `Product` use `ClassVar` registries
- Global state can cause issues in tests (state persists between tests)
- **Consider**: pytest fixtures to reset registries

### Complex Spatial Code
- `components/aer/spatial/core.py` (521 lines) handles grid generation, UTM conversion, footprint calculation
- **Consider**: Split into smaller modules (grid generation, geometry helpers)

## Potential Issues

### Grid File Dependencies
- Grid parquet files must exist for `GridDefinition.load_grid()` to succeed
- No grid generation in core — relies on pre-existing files
- **Action**: Document grid generation workflow

### Plugin Discovery Complexity
- Entry points must be registered in BOTH:
  1. Project `pyproject.toml` (for distribution)
  2. Root `pyproject.toml` (for development)
- False discovery is a common footgun (documented in README)

### Version Constraints
- Python 3.13+ required (cutting edge)
- Some dependencies may have compatibility issues

## Security Considerations

### Credentials
- `EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD` in environment
- `CDSE_S3_*` credentials
- **Always**: Use environment variables, never hardcode

### S3 Access
- Public bucket access via `s3fs` with potential data egress costs
- **Action**: Validate URL patterns before download

## Performance Considerations

### Grid Operations
- `Grid.latlon2rowcol()` uses list comprehensions — can be slow for large inputs
- **Consider**: Vectorize with numpy

### Download Backends
- aria2 preferred for throughput (multi-connection)
- Pure Python fallback uses `ThreadPoolExecutor`
- **Consider**: Async downloader using `aiohttp`

## Fragile Areas

### Spatial Footprint Calculation
- `get_bounded_footprint()` in `Grid` class has edge cases for boundary rows/columns
- Complex conditional logic for row/col indexing

### UTM Zone Detection
- Relies on `utm` library behavior
- Edge cases near zone boundaries may produce unexpected results

### Polylith Configuration
- `hatch-polylith-bricks` build hook required for proper wheel creation
- Missing entry in `build.targets.wheel.packages` causes silent failures

## Known Limitations

- Only supports Python 3.13+ (no older versions)
- No async search methods (currently synchronous)
- Grid system designed for specific resolutions (km-based)
- No built-in authentication caching
