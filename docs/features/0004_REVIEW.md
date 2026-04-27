# Code review: Feature 0004 (temporal alignment)

**Scope:** implementation vs `docs/features/0004_PLAN.md` (alignment across inspections and change-event APIs).  
**Artifacts reviewed:** `backend/app/**`, `backend/alembic/**`, `backend/tests/**`.  
**Validation run:** `python -m pytest -q` in `backend` — **36 passed**.

## Findings (ordered by severity)

### High: baseline selection is not constrained to prior inspections

`_select_baseline_inspection` in `app/services/alignment.py` does not enforce that baseline is earlier than target (by capture timestamp or created timestamp).  
It can select a newer inspection as "baseline", which violates the plan’s “candidate prior inspections” behavior and can invert appeared/disappeared semantics.

### High: matching ignores configured geo/time tolerances

`match_detection_sets` only applies class/type + IoU + confidence filtering.  
`alignment_geo_tolerance_meters` and per-pair time tolerance behavior are configured in settings but not used in matching/gating logic, so key plan constraints are currently non-functional.

### Medium: missing pairwise compare API from plan

Plan calls out pairwise compare using `baseline_inspection_id` + `target_inspection_id`.  
Current API only exposes target-inspection scoped reads:
- `GET /ingest/{inspection_id}/alignment`
- `GET /ingest/{inspection_id}/changes`  
Useful, but not equivalent to explicit pairwise comparison endpoint behavior.

### Medium: alignment endpoint filtering is narrower than planned

Plan specifies filters including `asset_zone_id`, `change_type`, and class/type options.  
Current `GET /ingest/{inspection_id}/alignment` supports only `asset_zone_id` and `change_type`; class/type filtering is absent.

### Medium: asset/zone fallback key does not follow planned precedence

`build_asset_zone_id` in `app/services/asset_zone.py` falls back to:
- `asset_zone_hint`, then
- `extra_attributes.site_hint`, class, centroid bucket.  

The plan’s precedence includes explicit `asset_hint` + class and site/geospatial grouping. Current implementation does not consume inspection `asset_hint` at key-derivation time, and inference attributes usually do not include site hints, so many keys collapse to `site-unknown:*`.

### Low: route module is becoming overloaded

`app/api/routes/ingest.py` now contains upload, frame, detection, alignment, and change endpoints.  
Functionality is fine, but this file is growing into multiple bounded contexts; a dedicated `alignment` route module (as suggested by plan) would improve maintainability.

## Plan alignment snapshot

- **Implemented well:** new alignment/change models + migration, inspection status/count fields, worker invoking alignment after detections, alignment pair + change-event persistence, pagination envelopes for alignment/change APIs, and matching/service tests.
- **Partial/missing:** true prior-inspection baseline policy, geo/time gating in matching, pairwise compare endpoint, broader alignment filtering (class/type), and plan-prescribed asset-zone precedence.

## Open questions / assumptions

- Assumed “prior inspections” means baseline should be strictly earlier than target when timestamps exist.
- Assumed geo/time tolerance settings are expected to influence per-pair acceptance, not just cohort selection.
- Assumed pairwise compare endpoint is still required even with target-inspection-scoped list endpoints.

## Summary

Feature 0004 is substantially built and test-covered, but two core behavior gaps remain before it fully matches the plan:  
1) baseline can be selected from newer inspections, and  
2) geo/time tolerance gating is not applied in matching.  
Addressing those, plus adding the pairwise compare/filter surfaces, will bring the implementation in line with the intended temporal-alignment contract.
