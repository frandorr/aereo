# Architecture

## Pattern: Polylith

`aer` follows the [Polylith architecture](https://davidvujic.github.io/python-polylith-docs/) with:

- **Components**: Reusable functional blocks (`components/aer/*`)
- **Bases**: Entry points/IO boundaries (`bases/aer/*`)
- **Projects**: Deployable artifacts (`projects/*`)
- **Development**: Workspace helpers (`development/`)

## Layers

```
┌─────────────────────────────────────────┐
│           Projects (deployable)          │
│  - aer-core (main)                       │
│  - aer-search-xxx (plugins)              │
└─────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────┐
│    Bases (entry points, I/O boundaries)   │
│  - download_api (download orchestrator) │
└─────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────┐
│   Components (business logic, pure)      │
│  - search     - spectral    - temporal  │
│  - spatial    - downloader  - settings   │
│  - plugin     - bootstrap   - goes_fetcher│
└─────────────────────────────────────────┘
```

## Data Flow

```
Search Query
    │
    ▼
┌─────────────────────────────────────────┐
│  SearchPlugin Protocol                  │
│  (earthaccess / aws-goes / etc.)       │
└─────────────────────────────────────────┘
    │
    ▼ (returns validated GeoDataFrame)
┌─────────────────────────────────────────┐
│  Download Orchestrator (download_api)   │
│  - Auto-selects backend (aria2c/raw)   │
└─────────────────────────────────────────┘
    │
    ▼ (returns DownloadedResultSchema)
Spatial Processing / Resampling
```

## Key Abstractions

### Plugin System

```python
# components/aer/plugin/core.py
@plugin(name="earthaccess", category="search")
def my_search(query: SearchQuery) -> GeoDataFrame[SearchResultSchema]:
    ...
```

- **Registry**: `PluginRegistry` — discovers via `entry_points`, builds capability graph
- **Pipeline**: `Pipeline` — chains typed plugins with type-safe transitions

### Domain Models (attrs.frozen)

- `components/aer/spectral/` — `Instrument`, `Satellite`, `Band`, `Channel`, `Product`
- `components/aer/spatial/` — `GridCell`, `GridSpatialExtent`, `GridDefinition`
- `components/aer/temporal/` — `TimeRange`
- `components/aer/search/` — `SearchQuery`, `SearchResultSchema`

### Data Schemas (Pandera)

```python
# components/aer/search/core.py
class SearchResultSchema(pa.DataFrameModel):
    product_name: Series[pa.String]
    granule_id: Series[pa.String]
    geometry: GeoSeries[Any]
    ...
```

## Entry Points

| Entry Point | File | Purpose |
|-------------|------|---------|
| `aer.plugins` | `components/aer/plugin/core.py` | Plugin registry discovery |
| `aer.plugins.search` | Per-project `pyproject.toml` | Search method registration |

## Error Handling

- **returns**: `Result`, `Maybe` monads for composable error handling
- **attrs.validators**: Runtime validation for domain objects
- **pandera**: DataFrame schema validation
