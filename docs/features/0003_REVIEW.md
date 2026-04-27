# Code review: Feature 0003 (detections + classification)

**Scope:** implementation vs `docs/features/0003_PLAN.md` for detection/classification.  
**Artifacts reviewed:** `backend/app/**`, `backend/alembic/**`, `backend/tests/**`.  
**Validation run:** `python -m pytest -q` in `backend` — **28 passed**.

## Findings (ordered by severity)

### High: detection API does not return geometry/attributes despite persistence

`Detection` persists geometry (`geometry`) and optional attributes (`attributes`), but `DetectionPublic` omits both fields.  
This means clients cannot query the geometry output of inference even though the plan explicitly scopes geometry persistence and queryable inspection/frame detection results.

### Medium: detection list API is not truly paginated response shape

Plan calls for a paginated list response schema, but `GET /ingest/{inspection_id}/detections` and frame-level detections currently return raw `list[DetectionPublic]` only (no `total`, `limit`, `offset`, etc).  
Functional filtering works, but response contract is thinner than planned and less useful for UI/consumer paging.

### Medium: detection job hints do not support enabled-classes contract

Plan mentions detection hints including enabled classes / overrides. `IngestJobMessage.detection` currently supports threshold/model only and pipeline ignores any class-level allowlist policy.  
This is a partial implementation gap in the job contract surface.

### Low: detection endpoint exact class filtering may surprise clients

`class_name` filter is exact match with no normalization. Taxonomy and persisted labels are lowercase, so mixed-case query values silently return no rows.  
Not incorrect, but API behavior should be documented or normalized for consistency.

## Plan alignment snapshot

- **Implemented well:** inference config settings, detection model + migration/indexes, inspection detection status/count fields, taxonomy mapping, threshold filtering, worker detection stage, detection failure status/error persistence, and API endpoints for inspection/frame detection reads.
- **Partial/missing:** response schema pagination envelope, geometry/attributes exposure in read schemas, richer detection hints (`enabled_classes`), and dedicated `test_worker_detection.py` file (worker behavior is covered in `test_ingest_service.py` instead).

## Open questions / assumptions

- Assumed geometry/attributes are intended to be externally consumable (not just internal storage), since they are part of the feature scope.
- Assumed “paginated response” means explicit envelope schema rather than query params alone.
- Assumed unknown labels should continue being dropped (current deterministic policy in inference layer).

## Summary

Feature 0003 is substantially implemented and test-backed, with good end-to-end flow from frames -> detections -> read APIs.  
The biggest remaining correctness gap is API contract completeness: detection geometry/attributes are persisted but not returned, and list endpoints are not modeled as paginated response objects as planned.
