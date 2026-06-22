# Architecture Overview

AEREO is a plugin-based satellite data extraction framework. Its goal is to give
users a single, consistent way to search many Earth-observation catalogs,
prepare analysis-ready extraction tasks, and execute them on a local machine or
in the cloud.

---

## What problem AEREO solves

Satellite data is scattered across many catalogs and formats:

- **Planetary Computer** for Sentinel-2 and other STAC collections.
- **NASA Earthdata** for MODIS, VIIRS, and Sentinel-3.
- **AWS open data** for GOES ABI.
- **Specialized catalogs** such as Tessera.

Each catalog has its own API, authentication, and file format. AEREO unifies
them behind a small set of interfaces so that researchers and data scientists
can focus on the science instead of the plumbing.

---

## High-level components

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User-facing layer                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Python API   │  │ Hydra CLI    │  │ Jupyter      │  │ AWS Lambda      │ │
│  │ AereoClient  │  │ aereo        │  │ notebooks    │  │ handler         │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘ │
└─────────┼─────────────────┼─────────────────┼───────────────────┼──────────┘
          │                 │                 │                   │
          └─────────────────┴─────────┬───────┴───────────────────┘
                                      │
                          ┌───────────▼────────────┐
                          │    ExtractionJob       │
│                         │  (search, grid, patch, │
                          │   extract, output_uri) │
                          └───────────┬────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
┌─────────▼─────────┐     ┌───────────▼───────────┐   ┌───────────▼───────────┐
│  Search plugins   │     │  Grid / Patch system  │   │  Execution backends   │
│  SearchProvider   │     │  Major TOM grid       │   │  LocalProcessBackend  │
│                   │     │  UTMGridConfig        │   │  ThreadBackend        │
└─────────┬─────────┘     └───────────┬───────────┘   │  LambdaBackend        │
          │                           │               └───────────┬───────────┘
          │                           │                           │
┌─────────▼───────────────────────────▼───────────────────────────▼───────────┐
│                         Extraction stage pipeline                            │
│    Reader → Pre-processors → Reprojector → Post-processors → Writer         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core ideas

### 1. One pipeline, many data sources

Every data source plugs into the same three-phase pipeline:

1. **Search** — find granules matching AOI + time.
2. **Prepare** — build grid cells and chunk into tasks.
3. **Execute** — run each task through a stage pipeline.

Changing the sensor means changing the config, not the orchestration code.

### 2. Declarative configs with Hydra

Pipelines are configured as Hydra config packages. A config package is just a
directory of YAML files that compose into an `ExtractionJob`. The same config
works with the Python API, the CLI, and the Lambda handler.

### 3. Stage plugins feel like PyTorch modules

Each stage plugin is a class with a `__call__` method. Implement a `Reader`,
`Processor`, `Reprojector`, or `Writer`, register it under the `aereo.plugins`
entry-point group, and it becomes available everywhere.

### 4. Analysis-ready output on a shared grid

Extraction results are written in the **EOIDS** convention on the **Major TOM
grid**. This makes multi-sensor stacking, mosaicking, and ML training
straightforward.

---

## Where to go next

- [Pipeline Architecture](../concepts/pipeline-architecture.md) for the exact data flow.
- [Execution Backends](../execution-backends.md) for parallelism and Lambda.
- [Visual Architecture Guide](architecture-visual.md) for diagrams.
- [Build Your First Plugin](../plugins/build-first-plugin.md) to extend AEREO.
