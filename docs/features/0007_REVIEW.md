# Feature 0007 — Code review (maintenance recommendations)

Reviewed against `docs/features/0007_PLAN.md` and `commands/code_review_05.md`.

## Plan coverage

| Plan item | Status |
|-----------|--------|
| Settings: weights, band cutoffs, SLA days per label, max per inspection | `recommend_*` fields in `app/core/config.py` |
| `MaintenanceRecommendation` model + indexes | `maintenance_recommendations`; migration ships as **`0006_add_maintenance_recommendations`** (revision `0006` after progression `0005`) — same content as plan’s “0007” slice, numbering differs from doc title only |
| `recommendation_count` (+ error metadata pattern) | On `Inspection`; engine sets `metadata.recommendation_error` and count `0` on failure paths |
| Pydantic `RecommendationPublic`, paginated list | `app/schemas/recommendations.py`; `PaginatedRecommendationsResponse` |
| `recommendation_rules.py` + `recommendation_engine.py` | Implemented; taxonomy reused via defect/hazard handling |
| Worker after progression | `ingest_ack.py` calls `run_recommendations_for_inspection` inside `try`/`except` so optional-stage failures do not fail the job |
| `GET /ingest/{inspection_id}/recommendations` + filters | `ingest.py`; `asset_zone_id` / `priority_label` filters |
| `POST .../rebuild` | Not implemented (plan optional v1 omit — OK) |
| `docs/INGEST_API.md` | SLA anchor, replace semantics, env table entries |
| Tests: rules, engine, API | `test_recommendation_rules.py`, `test_recommendation_engine.py`, `test_ingest_api.py` |

## Issues found and fixes

### 1. Zone scope omitted progression-only `asset_zone_id`s (fixed)

Plan §A requires distinct `asset_zone_id` values from change events, alignments, detections, **and** inputs used for progression. The engine built `zone_keys` from detections, change events, and alignments **before** loading progression metrics, so a zone that appeared **only** on `progression_metrics` never received a recommendation.

**Fix:** Load `ProgressionMetric` rows into `pm_by_zone` first, then `zone_keys = union(all four sources)`.

**Test:** `test_engine_includes_asset_zone_from_progression_only`.

### 2. Model field `title` (informational)

Plan lists optional `title` alongside `action_summary`. v1 persists a single `action_summary` column; API/schema match. No change unless product wants a separate title.

### 3. Worker exception path (informational)

`run_recommendations_for_inspection` normally swallows DB/logic errors and returns `0` after `_record_recommendation_error`. The worker wraps the call in `try`/`except` for unexpected raises (e.g. `ValueError` if inspection missing): those log a warning and return `0` without writing `recommendation_error` metadata. Rare in production; acceptable for v1.

## Data alignment / API

- JSON remains **snake_case** (`priority_rank`, `sla_target_at`, `action_summary`, `rationale` as a list of factor dicts with `kind` / `message` / `refs`).
- `rationale` refs use stringified UUIDs where needed for JSON compatibility (consistent with timeline `refs`).

## Style

- Engine and rules stay small; gating mirrors progression (`alignment_ready` before delete/rebuild).
- SLA uses `timedelta(seconds=days * 86400)` as documented in `INGEST_API.md` (calendar-day spirit).

## Tests

Full backend suite run after the zone-union fix: all green.
