# PRD: Unified AerProfile Refactor

## 1. Executive Summary

Today search and extraction configuration live in separate, untyped places:
- `collections` are passed directly to `AerClient.search()`
- `channels`, `satellite`, and other domain-specific config are hidden inside untyped `search_params` dicts
- `plugin_hints` are passed as a top-level mapping to the client
- `ExtractionProfile` is used only for extraction

This refactor unifies all of this into a single typed object — **`AerProfile`** — that is the ground truth for the entire pipeline. `AerProfile` replaces `ExtractionProfile`, carries `collections`, typed `channels` / `satellite`, and `plugin_hints`, and is accepted by both `search()` and `prepare_for_extraction()`.

**Scope:** `aer` core repo + all active plugin repos.
**Backward compatibility:** None. We control all call sites.

---

## 2. Naming Decision: `AerProfile`

`ExtractionProfile` is the wrong name once the same object drives `search()`. Users would be forced to reason about why an "extraction" thing is being passed to "search." `AerProfile` signals "this is the configuration for the AER pipeline" — simple, short, and accurate.

**Decision:** Rename `ExtractionProfile` → `AerProfile`. No alias, no deprecation shim.

---

## 3. `AerProfile` Specification

```python
import attrs
from collections.abc import Mapping, Sequence
from typing import Any


@attrs.frozen
class AerProfile:
    """Ground-truth configuration for a single search + extraction unit.

    A profile bundles together:
    - What to search for (collections, channels, satellite)
    - How to extract it (resolution, variables, reader, padding, resampling, calibration)
    - Which plugins to use (plugin_hints)

    One profile = one coherent pipeline configuration.
    """

    name: str
    resolution: float
    collections: Sequence[str] = attrs.field(factory=tuple)
    collection_variables_map: Mapping[str, Sequence[str]] = attrs.field(factory=dict)
    channels: Sequence[str] | None = None
    satellite: str | None = None
    reader: str | None = None
    padding: int | None = None
    resampling: str | None = None
    calibration: str | None = None
    plugin_hints: Mapping[str, str] = attrs.field(factory=dict)
    extra_params: Mapping[str, Any] = attrs.field(factory=dict)
```

**Field rules:**
- `plugin_hints` accepts optional keys `"search"` and `"extract"`. Values are plugin entry-point names (e.g. `"aer-search-aws-goes"`).
- `collections` replaces the old top-level `collections` arg to `AerClient.search()`.
- `channels` and `satellite` are promoted from untyped `search_params` to first-class fields.
- `extra_params` remains the escape hatch for anything not covered by explicit fields.

---

## 4. Interface Contract Changes

### 4.1 `SearchProvider` (abstract base)

**Before:**
```python
def search(
    self,
    collections: Sequence[str],
    intersects: BaseGeometry | None = None,
    start_datetime: datetime | None = None,
    end_datetime: datetime | None = None,
    search_params: Mapping[str, Any] | None = None,
) -> GeoDataFrame[AssetSchema]: ...
```

**After:**
```python
def search(
    self,
    profiles: Sequence[AerProfile],
    intersects: BaseGeometry | None = None,
    start_datetime: datetime | None = None,
    end_datetime: datetime | None = None,
    search_params: Mapping[str, Any] | None = None,
) -> GeoDataFrame[AssetSchema]: ...
```

`search_params` is retained as the escape hatch for runtime / meta-level params (credentials, timeouts, etc.). Domain-specific config (`channels`, `satellite`) moves onto `AerProfile`.

### 4.2 `Extractor.prepare_for_extraction()`

No signature change — it already accepted `profiles`. Only the internal type changes from `ExtractionProfile` to `AerProfile`.

### 4.3 `Extractor.extract()`

No signature change — it receives the profile via `ExtractionTask.profile`.

### 4.4 `ExtractionTask`

**Before:**
```python
profile: ExtractionProfile
```

**After:**
```python
profile: AerProfile
```

### 4.5 `AerClient.search()`

**Before:**
```python
def search(
    self,
    collections: Sequence[str],
    intersects: Optional[BaseGeometry | dict] = None,
    start_datetime: Optional[datetime] = None,
    end_datetime: Optional[datetime] = None,
    search_params: Optional[Mapping[str, Any]] = None,
    init_params: Optional[Mapping[str, Any]] = None,
    plugin_hints: Optional[Mapping[str, str | Sequence[str]]] = None,
    failure_mode: FailureMode = FailureMode.BEST_EFFORT,
) -> GeoDataFrame[AssetSchema]: ...
```

**After:**
```python
def search(
    self,
    profiles: Sequence[AerProfile],
    intersects: Optional[BaseGeometry | dict] = None,
    start_datetime: Optional[datetime] = None,
    end_datetime: Optional[datetime] = None,
    search_params: Optional[Mapping[str, Any]] = None,
    init_params: Optional[Mapping[str, Any]] = None,
    failure_mode: FailureMode = FailureMode.BEST_EFFORT,
) -> GeoDataFrame[AssetSchema]: ...
```

`collections` and `plugin_hints` are removed. Both now live on each `AerProfile`.

### 4.6 `AerClient.prepare_for_extraction()`

**Before:**
```python
def prepare_for_extraction(
    self,
    search_results: GeoDataFrame[AssetSchema],
    target_aoi: Optional[BaseGeometry | dict] = None,
    resolution: Optional[float] = None,
    uri: Optional[str] = None,
    profiles: Optional[Sequence[ExtractionProfile]] = None,
    prepare_params: Optional[Mapping[str, Any]] = None,
    init_params: Optional[Mapping[str, Any]] = None,
    plugin_hints: Optional[Mapping[str, str | Sequence[str]]] = None,
    target_grid_dist: Optional[int] = None,
    target_grid_overlap: Optional[bool] = None,
) -> Sequence[ExtractionTask]: ...
```

**After:**
```python
def prepare_for_extraction(
    self,
    search_results: GeoDataFrame[AssetSchema],
    target_aoi: Optional[BaseGeometry | dict] = None,
    resolution: Optional[float] = None,
    uri: Optional[str] = None,
    profiles: Optional[Sequence[AerProfile]] = None,
    prepare_params: Optional[Mapping[str, Any]] = None,
    init_params: Optional[Mapping[str, Any]] = None,
    target_grid_dist: Optional[int] = None,
    target_grid_overlap: Optional[bool] = None,
) -> Sequence[ExtractionTask]: ...
```

`plugin_hints` removed — extracted from each `AerProfile` instead.

### 4.7 `AerClient.extract_batches()`

No signature change. `ExtractionTask` already carries the profile.

---

## 5. Plugin Hint Resolution Rules

The client resolves the target plugin for a profile using **exactly one** source:

1. `profile.plugin_hints.get(plugin_type)` where `plugin_type` is `"searcher"` or `"extractor"`.
2. If absent, auto-discover from `profile.collections` using the registry.
3. If hinted plugin is not registered → `ValueError`.
4. If auto-discovery returns nothing → skip profile (search) or raise (extract).

There is no client-level override. The profile is the single ground truth.

---

## 6. Task Breakdown

### Phase 1 — Core (`aer` repo)

#### Task 1.1: Define `AerProfile` ✅ DONE
**File:** `components/aer/interfaces/core.py`
**Action:**
- Rename `ExtractionProfile` → `AerProfile`.
- Add fields: `collections`, `channels`, `satellite`, `plugin_hints`.
- Kept `ExtractionProfile = AerProfile` temporary alias to avoid breaking downstream code during transition (will be removed in Task 1.7).

**Tests:**
```python
def test_aer_profile_has_all_fields():
    profile = AerProfile(
        name="goes_16_abi",
        resolution=1000.0,
        collections=["ABI-L1b-RadC"],
        channels=["C01", "C02"],
        satellite="GOES-16",
        plugin_hints={"search": "aer-search-aws-goes", "extract": "aer-extract-aws-goes"},
    )
    assert profile.collections == ["ABI-L1b-RadC"]
    assert profile.channels == ["C01", "C02"]
    assert profile.satellite == "GOES-16"
    assert profile.plugin_hints["search"] == "aer-search-aws-goes"

def test_aer_profile_defaults():
    profile = AerProfile(name="minimal", resolution=100.0)
    assert profile.collections == ()
    assert profile.channels is None
    assert profile.satellite is None
    assert profile.plugin_hints == {}
```

#### Task 1.2: Update `ExtractionTask` ✅ DONE
**File:** `components/aer/interfaces/core.py`
**Action:** Changed `profile: ExtractionProfile` → `profile: AerProfile`. No `__attrs_post_init__` changes needed.

**Tests:**
```python
def test_extraction_task_accepts_aer_profile():
    profile = AerProfile(name="test", resolution=10.0, collections=["GOES"])
    task = ExtractionTask(
        assets=valid_gdf,
        profile=profile,
        uri="test",
        grid_cells=[],
    )
    assert task.profile.name == "test"
```

#### Task 1.3: Update `SearchProvider.search()` abstract signature ✅ DONE
**File:** `components/aer/interfaces/core.py`
**Action:** Updated abstract method signature: `collections` → `profiles`. Updated docstring. Added `from __future__ import annotations` to handle forward reference to `AerProfile`.

**Tests:**
```python
def test_search_provider_signature_has_profiles():
    import inspect
    sig = inspect.signature(SearchProvider.search)
    assert "profiles" in sig.parameters
    assert "collections" not in sig.parameters

def test_search_provider_accepts_profiles_signature():
    class GoodSearcher(SearchProvider):
        supported_collections = ["X"]
        def search(self, profiles, ...): ...
    searcher = GoodSearcher()
    assert searcher is not None
```

#### Task 1.4: Update `AerClient.search()` ✅ DONE
**File:** `bases/aer/client/core.py`
**Action:**
- Replaced `collections` param with `profiles`.
- Removed `plugin_hints` param.
- Refactored grouping logic: group `profiles` by resolved search plugin.
- Build `execution_groups: dict[(plugin_name, params_key), list[AerProfile]]`.
- Pass `profiles` (not `collections`) to `plugin.search()`.

**Tests:**
```python
def test_client_search_accepts_profiles(monkeypatch):
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]
    mock_searcher = MagicMock()
    mock_searcher.search.return_value = valid_df
    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)
    profile = AerProfile(name="p1", resolution=10.0, collections=["MODIS"])
    client.search(profiles=[profile])

    call_kwargs = mock_searcher.search.call_args.kwargs
    assert "profiles" in call_kwargs
    assert call_kwargs["profiles"][0].name == "p1"
```

#### Task 1.5: Update `AerClient.prepare_for_extraction()` plugin resolution ✅ DONE
**File:** `bases/aer/client/core.py`
**Action:**
- Removed `plugin_hints` param.
- Resolve extractor using `profile.plugin_hints.get("extract")` instead of client-level hints.
- Added fallback to search result collections for default profiles created from `resolution` arg.

**Tests:**
```python
def test_prepare_uses_profile_extract_hint(monkeypatch):
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.find_extractors_for.return_value = ["dummy_extractor"]
    mock_registry.has_extractor.return_value = True
    mock_extractor = MagicMock()
    mock_extractor.prepare_for_extraction.return_value = []
    mock_registry.get_extractor.return_value = mock_extractor

    client = AerClient(registry=mock_registry)
    profile = AerProfile(
        name="p1",
        resolution=10.0,
        collections=["MODIS"],
        plugin_hints={"extract": "my_extractor"},
    )
    client.prepare_for_extraction(
        search_results=valid_df, profiles=[profile], uri="s3://out"
    )
    mock_registry.get_extractor.assert_called_with("my_extractor")
```

#### Task 1.6: Update internal helpers ✅ DONE
**File:** `bases/aer/client/core.py`
**Action:**
- Replaced `_resolve_plugin_for_collection` with `_resolve_plugin_for_profile`.
- Removed `_normalize_hints` entirely since hints are no longer passed at client level.
- Updated `extract_batches` to resolve from profile hints.

**Tests:**
```python
def test_resolve_plugin_for_profile_uses_hint():
    client = AerClient(registry=mock_registry)
    profile = AerProfile(
        name="p1", resolution=10.0, collections=["X"],
        plugin_hints={"search": "hinted_searcher"}
    )
    mock_registry.has_searcher.return_value = True
    result = client._resolve_plugin_for_profile("searcher", profile)
    assert result == "hinted_searcher"

def test_resolve_plugin_for_profile_auto_discovers():
    client = AerClient(registry=mock_registry)
    profile = AerProfile(name="p1", resolution=10.0, collections=["MODIS"])
    mock_registry.find_searchers_for.return_value = ["auto_searcher"]
    result = client._resolve_plugin_for_profile("searcher", profile)
    assert result == "auto_searcher"
```

#### Task 1.7: Update core tests ✅ DONE
**File:** `test/bases/aer/client/test_core.py`, `test/components/aer/interfaces/test_core.py`
**Action:** Updated all call sites that use `ExtractionProfile` or pass `collections` / `plugin_hints` to `AerClient` methods. Added new tests for `_resolve_plugin_for_profile`, profile-based search hints, and profile-based extract hints. All 39 interface + client tests pass. Type check: 0 errors, 0 warnings, 0 notes.

---

### Phase 2 — Search Plugins (active)

#### Task 2.1: `aer-search-aws-goes` ✅ DONE
**File:** `components/aer/search_aws_goes/core.py`
**Action:**
- Update `search()` signature to accept `profiles: Sequence[AerProfile]`.
- Extract collections: `[c for p in profiles for c in p.collections]`.
- Extract `channels` from union across profiles instead of `search_params["channels"]`.
- Extract `satellite` from union across profiles instead of `search_params["satellites"]` / `search_params["satellite"]`.
- Remove reliance on `search_params` for domain config.

**Tests:**
```python
def test_search_reads_collections_from_profiles():
    profile = AerProfile(
        name="goes", resolution=1000.0,
        collections=["ABI-L1b-RadC"],
        satellite="GOES-16",
    )
    result = plugin.search(profiles=[profile], ...)
    assert all(r.collection == "ABI-L1b-RadC" for r in result)

def test_search_filters_by_profile_channels():
    profile = AerProfile(
        name="goes", resolution=1000.0,
        collections=["ABI-L1b-RadC"],
        channels=["C01"],
    )
    result = plugin.search(profiles=[profile], ...)
    assert all(r.channel_id == "1" for r in result)
```

**Result:** All 6 unit tests pass. Type check: 0 errors, 0 warnings, 0 notes.

#### Task 2.2: `aer-search-earthaccess`
**File:** `components/aer/search_earthaccess/core.py`
**Action:** Same refactor as 2.1. Extract collections from `profiles`. No channels/satellite specific logic here, but update signature.

**Tests:**
```python
def test_search_reads_collections_from_profiles():
    profile = AerProfile(name="modis", resolution=1000.0, collections=["VNP02IMG"])
    result = plugin.search(profiles=[profile], ...)
    assert len(result) > 0
```

#### Task 2.3: `aer-search-planetary-computer`
**File:** `components/aer/search_planetary_computer/core.py`
**Action:** Same refactor as 2.1. Extract collections and channels from `profiles`.

**Tests:**
```python
def test_search_reads_collections_from_profiles():
    profile = AerProfile(
        name="pc", resolution=10.0, collections=["sentinel-2-l2a"], channels=["B02"]
    )
    result = plugin.search(profiles=[profile], ...)
    assert all(r.collection == "sentinel-2-l2a" for r in result)
```

---

### Phase 3 — Extract Plugins (active)

#### Task 3.1: `aer-extract-aws-goes`
**File:** `components/aer/extract_aws_goes/core.py`
**Action:**
- Update type hints referencing `ExtractionProfile` → `AerProfile`.
- Read `channels` and `satellite` from `extraction_task.profile.channels` / `.satellite` when available, falling back to merged params for internal consistency during transition.
- Update docstrings.

**Tests:**
```python
def test_extract_reads_satellite_from_profile():
    profile = AerProfile(
        name="goes", resolution=1000.0,
        collections=["ABI-L1b-RadC"],
        satellite="GOES-16",
        collection_variables_map={"ABI-L1b-RadC": ["C01"]},
    )
    task = make_task(profile=profile)
    result = extractor.extract(task)
    assert len(result) > 0
```

#### Task 3.2: `aer-extract-satpy`
**File:** `components/aer/extract_satpy/core.py`
**Action:** Same as 3.1. Update type hints and docstrings. Read `reader`, `satellite`, `padding`, `resampling`, `calibration` from typed profile fields.

**Tests:**
```python
def test_extract_reads_reader_from_profile():
    profile = AerProfile(
        name="satpy", resolution=1000.0,
        collections=["VJ202IMG"],
        reader="viirs_l1b",
        collection_variables_map={"VJ202IMG": ["I01"]},
    )
    task = make_task(profile=profile)
    result = extractor.extract(task)
    assert len(result) > 0
```

#### Task 3.3: `aer-extract-odc-stac`
**File:** `components/aer/extract_odc_stac/core.py`
**Action:** Same as 3.1. Update type hints. Read bands from `task.profile.collection_variables_map` and `task.profile.resolution` as already done — just ensure `AerProfile` type is used.

**Tests:**
```python
def test_extract_accepts_aer_profile():
    profile = AerProfile(
        name="odc", resolution=10.0,
        collections=["sentinel-2-l2a"],
        collection_variables_map={"sentinel-2-l2a": ["B04"]},
    )
    task = make_task(profile=profile)
    result = extractor.extract(task)
    assert len(result) > 0
```

---

### Phase 4 — Plugin Template

#### Task 4.1: Update `aer-plugin-template`
**Files:** `setup.sh`, scaffold `core.py` files, `README.md`
**Action:**
- Update search scaffold to accept `profiles: Sequence[AerProfile]`.
- Update extract scaffold to reference `AerProfile`.
- Update README examples.

**Tests:**
```python
def test_template_search_scaffold_uses_profiles():
    # After running setup.sh, the generated search plugin
    # should have `profiles` in its search() signature.
    import inspect
    sig = inspect.signature(GeneratedSearchPlugin.search)
    assert "profiles" in sig.parameters

def test_template_extract_scaffold_uses_aer_profile():
    import ast
    source = (Path("components") / "..." / "core.py").read_text()
    tree = ast.parse(source)
    assert "AerProfile" in source
```

---

### Phase 5 — Integration Validation

#### Task 5.1: End-to-end profile-driven search
**File:** New or existing integration test in `aer` repo
**Action:** Create a test that constructs `AerProfile` with `plugin_hints`, calls `AerClient.search()`, and verifies the hinted plugin is used.

**Test:**
```python
def test_e2e_search_with_profile_plugin_hint(monkeypatch):
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.has_searcher.return_value = True
    mock_searcher = MagicMock()
    mock_searcher.search.return_value = empty_gdf
    mock_registry.get_searcher.return_value = mock_searcher

    client = AerClient(registry=mock_registry)
    profile = AerProfile(
        name="goes",
        resolution=1000.0,
        collections=["ABI-L1b-RadC"],
        satellite="GOES-16",
        plugin_hints={"search": "aer-search-aws-goes"},
    )
    client.search(profiles=[profile])
    mock_registry.get_searcher.assert_called_once_with("aer-search-aws-goes")
```

#### Task 5.2: End-to-end profile-driven extract
**File:** New or existing integration test in `aer` repo
**Action:** Create a test that constructs `AerProfile` with `plugin_hints`, runs `prepare_for_extraction` + `extract_batches`, and verifies the hinted extractor is used.

**Test:**
```python
def test_e2e_extract_with_profile_plugin_hint(monkeypatch):
    mock_registry = MagicMock(spec=AerRegistry)
    mock_registry.has_extractor.return_value = True
    mock_registry.find_extractors_for.return_value = []
    mock_extractor = MagicMock()
    mock_extractor.extract_batches.return_value = empty_artifact_gdf
    mock_registry.get_extractor.return_value = mock_extractor

    client = AerClient(registry=mock_registry)
    profile = AerProfile(
        name="goes",
        resolution=1000.0,
        collections=["ABI-L1b-RadC"],
        plugin_hints={"extract": "aer-extract-aws-goes"},
    )
    task = ExtractionTask(assets=valid_gdf, profile=profile, uri="test", grid_cells=[])
    client.extract_batches([task])
    mock_registry.get_extractor.assert_called_once_with("aer-extract-aws-goes")
```

#### Task 5.3: Cross-repo smoke test
**Action:** In each plugin repo, run the existing test suite after core changes. All tests must pass without `ExtractionProfile` references.

---

## 7. Skipped Repos

The following repos are **not** updated as part of this refactor:
- `aer-search-pc-sentinel2` (deprecated)
- `aer-extract-pc-sentinel2` (deprecated)

---

## 8. Checklist for Plugin Authors (Internal)

When updating an existing plugin repo:
1. [ ] Update `search()` signature to accept `profiles: Sequence[AerProfile]`
2. [ ] Extract collections from `profiles` instead of `collections` param
3. [ ] Extract `channels` / `satellite` from `profiles` instead of `search_params`
4. [ ] Update any references to `ExtractionProfile` → `AerProfile`
5. [ ] Update tests to construct `AerProfile` with `collections` field
6. [ ] Run tests and verify zero references to `ExtractionProfile` remain
