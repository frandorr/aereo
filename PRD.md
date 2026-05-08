# PRD: Per-Profile Downloader Configuration

## 1. Problem Statement

`downloader` is currently passed via `extract_params` to `client.extract_batches()`:

```python
client.extract_batches(
    tasks,
    extract_params={"downloader": earthaccess_download_wrapper},
)
```

This applies the **same downloader to every task in the batch**. In a multi-source pipeline (e.g. VIIRS via earthaccess + GOES via direct S3), different profiles need different download strategies. The downloader should be configurable **per-profile**, not per-batch.

## 2. Solution Overview

Add `downloader` as a first-class typed field on `AerProfile`. Extract plugins read `profile.downloader` first, falling back to `extract_params["downloader"]` for backward compatibility during the transition. This allows each `AerProfile` to declare its own download strategy.

## 3. Specification

### 3.1 `AerProfile` field addition

```python
@attrs.frozen
class AerProfile:
    # ... existing fields ...

    downloader: Downloader | None = None
    extra_params: Mapping[str, Any] = attrs.field(factory=dict)
```

- `Downloader` is the existing Protocol in `aer.interfaces.core` (`Callable[[str, Path], None]`).
- Default is `None` → extractor uses its built-in download logic.

### 3.2 Precedence rule

When an extractor needs a downloader, it resolves in this order:

1. `extraction_task.profile.downloader` — per-profile, highest priority
2. `extract_params.get("downloader")` — batch-level fallback # This can be ignored actually, downloader is set only in AerProfile.
3. Built-in default (e.g. plain HTTP or S3 anonymous)

### 3.3 Impact scope

- `aer` core repo: `AerProfile` definition + docstring updates
- `aer-extract-satpy`: reads `profile.downloader` explicitly
- `aer-extract-aws-goes`: reads `profile.downloader` explicitly
- `aer-extract-odc-stac`: reads `profile.downloader` explicitly
- `examples/extraction/extraction_example.py`: move `downloader` into profile

## 4. Task Breakdown

### Phase 1 — Core (`aer` repo)

#### Task 1.1: Add `downloader` field to `AerProfile` ✅
**File:** `components/aer/interfaces/core.py`
**Action:** Add `downloader: Downloader | None = None` to `AerProfile`. Update class docstring to document the field.

**Tests:**
```python
def test_aer_profile_accepts_downloader():
    def my_dl(url: str, path: Path) -> None:
        pass

    profile = AerProfile(
        name="test", resolution=100.0, downloader=my_dl
    )
    assert profile.downloader is my_dl

def test_aer_profile_downloader_defaults_to_none():
    profile = AerProfile(name="test", resolution=100.0)
    assert profile.downloader is None
```

#### Task 1.2: Update `Extractor.extract()` docstring ✅
**File:** `components/aer/interfaces/core.py`
**Action:** Document in `Extractor.extract()` docstring that `downloader` is read from `extraction_task.profile.downloader` first, then `extract_params`.

### Phase 2 — Extract Plugins

#### Task 2.1: `aer-extract-satpy` ✅
**File:** `components/aer/extract_satpy/core.py`
**Action:**
- Replaced `downloader = params.get("downloader")` with explicit precedence logic:
  ```python
  downloader = (
      extraction_task.profile.downloader
      or extract_params.get("downloader")
  )
  ```

**Tests:** Added three tests in `test/components/aer/extract_satpy/test_core.py`:
- `test_extract_uses_profile_downloader` — verifies profile-level downloader is passed to `download_asset_safely`
- `test_extract_falls_back_to_batch_downloader` — verifies batch-level fallback works
- `test_extract_prefers_profile_downloader_over_batch` — verifies profile wins when both are present

All tests pass (3/3). basedpyright reports 0 new errors (3 pre-existing unrelated errors in satpy typing).

#### Task 2.2: `aer-extract-aws-goes`
**File:** `components/aer/extract_aws_goes/core.py`
**Action:** Add the same precedence logic. Currently this plugin uses `download_asset_safely` directly without a custom downloader; add support for `profile.downloader` override.

**Tests:**
```python
def test_extract_uses_profile_downloader():
    mock_downloader = MagicMock()
    profile = AerProfile(
        name="test", resolution=1000.0,
        collections=["ABI-L1b-RadF"],
        downloader=mock_downloader,
    )
    task = make_task(profile=profile)
    # Verify downloader precedence is respected
```

#### Task 2.3: `aer-extract-odc-stac`
**File:** `components/aer/extract_odc_stac/core.py`
**Action:** Add the same precedence logic for `downloader`.

**Tests:**
```python
def test_extract_uses_profile_downloader():
    mock_downloader = MagicMock()
    profile = AerProfile(
        name="test", resolution=10.0,
        collections=["sentinel-2-l2a"],
        downloader=mock_downloader,
    )
    task = make_task(profile=profile)
    # Verify downloader precedence is respected
```

### Phase 3 — Example

#### Task 3.1: Update extraction example
**File:** `examples/extraction/extraction_example.py`
**Action:**
- Move `downloader=earthaccess_download_wrapper` from `extract_params` into the relevant `AerProfile.extra_params` or the new `downloader` field.
- Since earthaccess is only needed for earthaccess-backed collections (VIIRS, MODIS, OLCI), add it only to those profiles. GOES uses direct S3 and doesn't need it.

**Before:**
```python
extract_params = {
    "downloader": earthaccess_download_wrapper,
}
results_df = client.extract_batches(
    tasks,
    extract_params=extract_params,
    max_batch_workers=2,
)
```

**After:**
```python
profiles = [
    AerProfile(
        name="viirs_i1",
        resolution=375,
        collections=["VJ202IMG", "VJ203IMG"],
        # ... other fields ...
        downloader=earthaccess_download_wrapper,
    ),
    AerProfile(
        name="goes_c01",
        resolution=1000,
        collections=["ABI-L1b-RadF"],
        # ... other fields ...
        # No downloader — uses direct S3
    ),
    # ... etc
]

results_df = client.extract_batches(
    tasks,
    max_batch_workers=2,
)
```

### Phase 4 — Integration Tests

#### Task 4.1: Mixed-profile downloader test
**File:** `test/bases/aer/client/test_core.py` or new integration test
**Action:** Create two profiles with different downloaders (or one with, one without). Verify each task receives the correct downloader.

**Test:**
```python
def test_extract_batches_uses_profile_specific_downloaders(monkeypatch):
    dl_a = MagicMock()
    dl_b = MagicMock()

    profile_a = AerProfile(name="a", resolution=100.0, downloader=dl_a)
    profile_b = AerProfile(name="b", resolution=100.0, downloader=dl_b)

    task_a = make_task(profile=profile_a)
    task_b = make_task(profile=profile_b)

    # Mock extractor to capture which downloader was passed
    mock_extractor = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_extractor.return_value = mock_extractor
    mock_registry.has_extractor.return_value = True

    client = AerClient(registry=mock_registry)
    client.extract_batches([task_a, task_b])

    # Both tasks should have been processed; the mock extractor
    # can assert the downloader was available in the task profile
```

#### Task 4.2: Batch-level fallback test
**Action:** Verify that `extract_params["downloader"]` still works when `profile.downloader` is `None`.

**Test:**
```python
def test_extract_falls_back_to_batch_downloader():
    profile = AerProfile(name="no_dl", resolution=100.0)
    task = make_task(profile=profile)
    batch_downloader = MagicMock()
    # Verify batch-level downloader is used when profile.downloader is None
```

## 5. Checklist

When updating an extract plugin:
1. [ ] Read `extraction_task.profile.downloader` first
2. [ ] Fall back to `extract_params.get("downloader")`
3. [ ] Pass the resolved downloader to `download_asset_safely()`
4. [ ] Update plugin tests to cover both profile-level and batch-level downloader
