# Requirements: aer Plugin Extraction System

**Defined:** 2026-03-19
**Core Value:** Users can search data from any satellite provider and extract it to a standardized grid in a consistent way, regardless of source.

## v1 Requirements

### Extraction System

- [ ] **EXTR-01**: Extract plugin receives SearchResultSchema GeoDataFrame as input
- [ ] **EXTR-02**: Extract plugin returns file paths (local disk or S3 URLs)
- [ ] **EXTR-03**: Extract plugin handles reprojection to majortom grid internally
- [ ] **EXTR-04**: User specifies target cells via GridSpatialExtent
- [ ] **EXTR-05**: Extract plugins registered via entry points in pyproject.toml

### Pipeline Integration

- [ ] **PIPE-01**: Pipeline orchestrates search → extract flow
- [ ] **PIPE-02**: aer-core defines extract plugin interface
- [ ] **PIPE-03**: Bootstrap discovers extract plugins alongside search plugins

### Example Plugin

- [ ] **AWSG-01**: aws-goes-extract plugin implemented
- [ ] **AWSG-02**: aws-goes-extract conforms to extract plugin interface
- [ ] **AWSG-03**: aws-goes-extract project with proper entry points

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-band fusion | Each plugin handles its own bands |
| Built-in visualization | Out of scope for extraction pipeline |
| Direct data processing | Users own extracted data post-pipeline |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXTR-01 | Phase 1 | Pending |
| EXTR-02 | Phase 1 | Pending |
| EXTR-03 | Phase 1 | Pending |
| EXTR-04 | Phase 1 | Pending |
| EXTR-05 | Phase 1 | Pending |
| PIPE-01 | Phase 2 | Pending |
| PIPE-02 | Phase 2 | Pending |
| PIPE-03 | Phase 2 | Pending |
| AWSG-01 | Phase 3 | Pending |
| AWSG-02 | Phase 3 | Pending |
| AWSG-03 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 11 total
- Mapped to phases: 11
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-19*
