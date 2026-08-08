# FSD: Job config snapshot guard (job.yaml)

## Goal

Prevent silent output corruption when an EOIDS job name is reused with a
different configuration. On each job run, write a canonical YAML snapshot of
the job's output-defining config to `{output_uri}/job-<name>/job.yaml`; if a
snapshot already exists, compare it with the incoming job and raise a
descriptive error on mismatch. This restores the original `profile.json`/
`job.json` provenance intent (serialize the extraction config next to the
data, lost since `5ebc685`/`68e94f7`) and adds the missing validation half.

## Context and Evidence

- `ExtractionJob` (`components/aereo/pipeline/core.py:148`) is a frozen
  Pydantic model. Both construction paths — Hydra YAML (`from_yaml`,
  `load_from_config`) and in-code (`ExtractionJob(...)` with partials) —
  converge on the *same instantiated object*: scalar fields plus
  `functools.partial` callables with bound keywords. This is the key fact
  that resolves the "YAML job vs identical in-code job" question: compare
  canonical serializations of the instantiated job, never source text.
  Copying the source YAML would false-positive on comments, key order,
  helper vars (`target_bands`, `aoi_path` in
  `examples/config/job_sentinel2.yaml`), and interpolations.
- The band set is not a job field: it lives in the search provider's bound
  keywords (`collections: {sentinel-2-l2a: [red, nir]}`), so the snapshot
  must canonicalize callable keywords, not just job scalars.
- Extent parameters (`intersects`, `start_datetime`, `end_datetime`,
  `target_aoi`) change *which* scenes/cells are produced, not *how* data is
  transformed. Filenames already disambiguate them (`loc-`, `start-`/`end-`,
  `date-` segments), so extending a time range or AOI must NOT trigger the
  guard. They are excluded from identity.
- `job.execute()` (`pipeline/core.py:477`) is the single per-run entry point
  before any task runs — the natural hook (once per job, not per file).
- `_write_job_meta`/`meta_dict` in `eoids/core.py:56` is dead plumbing (no
  caller passes `meta_dict`); it is replaced by this feature.

## Proposed Design

New brick `components/aereo/jobguard/core.py`, wired into
`ExtractionJob.execute()` before executor dispatch. Pure functions,
no state.

1. `canonicalize_job(job: ExtractionJob) -> dict`
   - Scalars: `grid_dist`, `grid_resolution`, `margin`, `crop_buffer`,
     `grid_cells_margin`, `alignment_resolution`, `reproject_mode`.
   - Excluded: `name` (it is the lookup key), `output_uri` (where, not
     what), `overwrite` (runtime behavior), `target_aoi` (extent).
   - Callables (`read`, `write`, `preprocess`, `postprocess`, `reproject`,
     `search_provider`, `task_builder`): recursively unwrap
     `functools.partial` into
     `{_target_: "<module>.<qualname>", kw: canonical(value), ...}` with
     sorted keys. Geometries normalize to WKT via
     `normalize_geometry_input`. Non-serializable leaf values fall back to
     `repr()` (deterministic for the same process; documented limitation).
   - Extent-key exclusion applied recursively to callable keywords:
     `intersects`, `aoi`, `start_datetime`, `end_datetime`, `datetime`.
2. `check_job_snapshot(job: ExtractionJob) -> Path`
   - Snapshot path: `{output_uri}/job-{sanitize(name)}/job.yaml` (job-root
     level, not buried in `date-` dirs).
   - No snapshot exists → mkdir, write canonical YAML (`yaml.safe_dump`,
     `sort_keys=True`), return.
   - Snapshot exists → `yaml.safe_load`, deep-compare with the canonical
     dict. Mismatch → `JobConfigMismatchError(ValueError)` listing the
     differing key paths with old/new values, and the resolution hint:
     rename the job or delete the job directory.
3. Wire-up: `ExtractionJob.execute()` calls `check_job_snapshot(self)`
   first, guarded by a keyword `validate_snapshot: bool = True` on
   `execute()` (escape hatch, default on).
4. URI support: local paths via `pathlib`; `s3://`/other URIs via
   `fsspec.open` (already a transitive dependency, used by
   `write_catalog`). Guard silently skips (logs a warning) on non-local URIs
   if fsspec resolution fails — never blocks a run on guard I/O errors
   other than a confirmed mismatch.
5. Remove the dead `write_job_meta`/`meta_dict` params from
   `build_eoids_path` (breaking, noted in CHANGELOG; nothing calls them).

## Complexity and Resources

| Data path | Time | Space | Notes |
| --------- | ---- | ----- | ----- |
| canonicalize_job | O(N) in config-tree nodes (N ≈ tens) | O(N) | CPU-trivial, runs once per job |
| snapshot read + deep-compare | O(N) | O(N) | one YAML file, a few KB |
| snapshot write | O(1) | O(1) | single small file, first run only |

Guard overhead is negligible against a network/ raster-bound extraction
run (I/O bound task; the guard adds one local file stat+read per run).

## Justification

- **Compare instantiated jobs, not source YAML**: both constructors funnel
  through `hydra.utils.instantiate`/`model_validate` into the same frozen
  model (Hydra docs, `hydra.utils.instantiate`; `pipeline/core.py:530-617`),
  so semantic equality of the canonical dict is exactly "same job". This
  answers the in-code-vs-YAML concern: not overkill, it falls out for free —
  and textual comparison would be the fragile option.
- **YAML as snapshot format**: house format (Hydra-native configs), human
  readable/diffable; `yaml.safe_dump`/`safe_load` avoid arbitrary-object
  tags (PyYAML docs). pyyaml is already a dependency via Hydra/OmegaConf.
- **`functools.partial` unwrapping**: partials expose `func`/`keywords`
  (Python stdlib docs); `_target_`-shaped dict mirrors the Hydra config the
  user recognizes, and matches `_callable_name` precedent in
  `pipeline/core.py:42`.
- **Extent exclusion**: overwrite requires identical (collection, cell,
  time) path segments; extent params only add *new* paths
  (`eoids/core.py:build_eoids_path`). Including them would block legitimate
  incremental dataset growth. The exclusion list is a documented,
  conservative default; a false positive is recoverable (delete the stale
  snapshot) while a false negative is silent corruption.
- **Hook at `execute()`**: once-per-job, before any write; per-file checks
  (raster header reading) would cost an open per timestep and depend on
  plugin writers persisting band names (Writer is a protocol,
  `interfaces/core.py:81`).
- Estimates flagged: N (config-tree size) assumed tens of nodes; no
  benchmark needed at this scale, validated by unit tests.

## Task Breakdown

- [ ] Task 1: `components/aereo/jobguard/{__init__.py,core.py}` —
  canonicalize_job, check_job_snapshot, JobConfigMismatchError —
  unit tests: YAML-loaded vs in-code equivalent job passes; changed
  variables/resolution/callable-kwarg fails with readable diff; extent-only
  change (datetimes, AOI) passes.
- [ ] Task 2: `components/aereo/pipeline/core.py` — call
  `check_job_snapshot` in `execute()` behind `validate_snapshot` — test:
  execute() raises on mismatched existing snapshot, writes on first run.
- [ ] Task 3: `components/aereo/eoids/core.py` — remove `write_job_meta`/
  `meta_dict` plumbing; update `test/components/aereo/eoids/test_paths.py`.
- [ ] Task 4: docs (`docs/user-guide/outputs.md`) + CHANGELOG entry —
  document snapshot semantics, exclusions, and the recovery procedure.
- [ ] Task 5: full test suite green (`rtk pytest`), ruff clean.

## Acceptance Criteria

- Re-running an unchanged job (YAML or in-code, either order) succeeds and
  reuses/updates outputs.
- Re-running a job with different bands, resolution, grid params, or
  callable kwargs under the same name raises `JobConfigMismatchError`
  naming the differing fields, before any file is written.
- Re-running with only datetime/AOI changes succeeds.
- `job.yaml` is written at `{output_uri}/job-<name>/job.yaml` on first run
  and is valid YAML loadable by `yaml.safe_load`.
- `pytest` green, no raster I/O added on the per-file write path.
