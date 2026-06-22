# AEREO Architecture — Simplified Visual Guide

> A clean, high-level map of the AEREO system. For deep implementation details, see [Pipeline Architecture](../concepts/pipeline-architecture.md).
>
> Rendered SVGs are available alongside this file: `aer-architecture-visualization-1.svg` through `aer-architecture-visualization-7.svg`.

---

## 1. AEREO at a Glance

Three entry points. One pipeline. GeoTIFF output.

```mermaid
flowchart TB
    classDef entry fill:#e1f5ff,stroke:#01579b,stroke-width:2px,color:#000
    classDef core fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#000
    classDef output fill:#f5f5f5,stroke:#616161,stroke-width:2px,color:#000

    subgraph IN[" "]
        CLI["CLI"]:::entry
        PY["Python"]:::entry
        LAM["Lambda"]:::entry
    end

    CORE["AereoClient"]:::core
    OUT["GeoTIFFs"]:::output

    CLI --> CORE
    PY --> CORE
    LAM --> CORE
    CORE --> OUT
```

---

## 2. The Pipeline

Always the same three steps.

```mermaid
flowchart LR
    classDef plugin fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef core fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#000
    classDef output fill:#f5f5f5,stroke:#616161,stroke-width:2px,color:#000

    S["Search"]:::plugin
    P["Prepare"]:::core
    E["Extract"]:::plugin
    O["EOIDS GeoTIFFs"]:::output

    S --> P
    P --> E
    E --> O
```

---

## 3. What's Inside

Four layers. Entry drives Core. Core orchestrates Plugins and Building Blocks.

```mermaid
flowchart LR
    classDef entry fill:#e1f5ff,stroke:#01579b,stroke-width:2px,color:#000
    classDef core fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#000
    classDef plugin fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef data fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000

    A["Entry"]:::entry
    B["AereoClient"]:::core
    C["Plugins"]:::plugin
    D["Building Blocks"]:::data

    A --> B
    B --> C
    B --> D
```

---

## 4. Plugin Discovery

Install a pip package. AEREO finds it automatically.

```mermaid
flowchart LR
    classDef entry fill:#e1f5ff,stroke:#01579b,stroke-width:2px,color:#000
    classDef data fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000
    classDef core fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#000

    PIP["pip install"]:::entry
    EP["entry-points"]:::data
    REG["Registry"]:::core
    USE["AereoClient"]:::core

    PIP --> EP
    EP --> REG
    REG --> USE
```

---

## 5. Execution Modes

Same tasks. Different backends.

```mermaid
flowchart TB
    classDef core fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#000
    classDef run fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000

    T["Tasks"]:::core
    S["Sequential"]:::run
    P["ProcessPool"]:::run
    TH["ThreadPool"]:::run
    L["Lambda"]:::run

    T --> S
    T --> P
    T --> TH
    T --> L
```

---

## 6. Component Map

| Layer | Component | What it does |
|-------|-----------|--------------|
| **Entry** | `aereo.cli` | Terminal commands (`search`, `run`, `plugins`) |
| **Entry** | `aereo.client` | Python API — `AereoClient` class |
| **Entry** | `aereo.lambda_handler` | AWS Lambda entrypoint |
| **Core** | `aereo.interfaces` | Contracts — `SearchProvider`, `Reader`, `Processor`, `Reprojector`, `Writer`, `GridConfig`, `ExtractConfig` |
| **Core** | `aereo.registry` | Plugin discovery via `entry_points` |
| **Data** | `aereo.schemas` | Pandera validation — `AssetSchema`, `ArtifactSchema`, `GridSchema` |
| **Data** | `aereo.grid` | MajorTOM tiling — `GridDefinition`, `GridCell` |
| **Data** | `aereo.spatial` | CRS helpers — UTM EPSG lookup, reprojection |
| **Run** | `aereo.backends` | Backends — `LocalProcessBackend`, `ThreadBackend`, `TaskRunner` |
| **Run** | `aereo.serialization` | Task serialization for remote transport |
| **Run** | `aereo.asset_downloader` | Safe multi-process downloading (S3/HTTP/local) |
| **Output** | `aereo.eoids` | File naming & folder conventions |
| **Output** | `aereo.viz` | Quick plotting helpers |

---

## 7. Data Shapes

What flows through the pipeline.

```mermaid
flowchart LR
    classDef data fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000
    classDef core fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#000

    A["AssetSchema"]:::data
    T["ExtractionTask"]:::core
    R["ArtifactSchema"]:::data

    A --> T
    T --> R
```

---

## 8. Project Layout

AEREO is a Polylith monorepo.

```mermaid
flowchart LR
    classDef base fill:#e1f5ff,stroke:#01579b,stroke-width:2px,color:#000
    classDef comp fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#000
    classDef proj fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px,color:#000

    P["projects/"]:::proj
    B["bases/"]:::base
    C["components/aereo/"]:::comp

    P --> B
    B --> C
    P --> C
```
