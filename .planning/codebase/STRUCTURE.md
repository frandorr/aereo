# Structure

## Directory Layout

```
aer/
├── bases/                    # Entry points, I/O boundaries
│   └── aer/download_api/     # Download orchestrator
│       ├── __init__.py
│       └── core.py
├── components/               # Reusable functional bricks
│   └── aer/
│       ├── bootstrap/        # Plugin initialization
│       ├── downloader/        # Download result schema
│       ├── downloader_aria2/  # aria2 backend
│       ├── downloader_raw/   # Pure Python fallback
│       ├── goes_fetcher/     # GOES-specific logic
│       ├── plugin/           # Registry & Pipeline
│       ├── search/           # Search query & results
│       ├── settings/         # Environment configuration
│       ├── spectral/         # Instruments, satellites, bands
│       ├── spatial/          # Grid systems, geometry
│       └── temporal/         # TimeRange
├── projects/                 # Deployable artifacts
│   └── aer-core/             # Main published package
│       ├── pyproject.toml
│       └── README.md
├── test/                     # Mirrors component structure
│   ├── bases/
│   ├── components/
│   └── integration/
├── development/               # Workspace helpers
├── docs/                     # Documentation
├── .agents/                  # Agent skills & scripts
└── .planning/                # Planning artifacts
```

## Component Conventions

Each component follows:
```
component/aer/<name>/
├── __init__.py      # Public API (exports via __all__)
└── core.py          # Implementation
```

## Key Files

| File | Purpose |
|------|---------|
| `bases/aer/download_api/core.py` | Smart download orchestrator |
| `components/aer/plugin/core.py` | Plugin registry & Pipeline |
| `components/aer/search/core.py` | SearchResultSchema, SearchQuery |
| `components/aer/spatial/core.py` | Grid system implementation |
| `components/aer/spectral/core.py` | Instrument/Satellite registries |
| `components/aer/settings/core.py` | Pydantic Settings |

## Naming Conventions

- **Components**: `snake_case` (e.g., `downloader_aria2`)
- **Classes**: `PascalCase` (e.g., `GridSpatialExtent`)
- **Functions**: `snake_case` (e.g., `download_aria2`)
- **Constants**: `SCREAMING_SNAKE_CASE` (e.g., `ENV_SETTINGS`)

## Public API Pattern

```python
# components/aer/search/__init__.py
from aer.search.core import SearchResultSchema, SearchQuery

__all__ = ["SearchResultSchema", "SearchQuery"]
```

## Test Structure

```
test/
├── bases/aer/download_api/test_core.py
└── components/aer/{component}/test_*.py
```

## Grid Data Files

Stored alongside spatial component:
```
components/aer/spatial/
├── core.py
└── grid_{name}_{dist}km.parquet
```
