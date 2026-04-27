# Feature 0010 — Code review (operator outcome feedback)

Reviewed against `docs/features/0010_PLAN.md`, `commands/code_review_05.md`, and `docs/PRODUCT_BRIEF.md` (outcomes for calibration + bounded risk refinement).

## Plan coverage

| Plan item | Status |
|-----------|--------|
| Append-only `outcome_feedbacks` model | `OutcomeFeedback` with `org_scope`, anchors, `detection_refs`, snapshot fields, `model_name` / `model_version` denormalized from primary detection |
| Alembic + `conftest` / `__init__` / `env.py` | `0009_add_outcome_feedbacks.py` (follows `0008` issue states) |
| Schemas `outcomes.py` | `OutcomeSubmitRequest`, `OutcomeFeedbackPublic`, `OutcomeListResponse` |
| Service: submit + list + zone prior | `outcome_feedback_service.py`; validation matrix; FK checks; best-effort recommendation snapshot |
| `POST /outcomes`, `GET /outcomes` | `app/api/routes/outcomes.py`, `main.py` |
| Phase 2: settings + `zone_feedback_score_adjustment` after `score_zone` / risk rules | `recommendation_engine.py` applies additive adjustment after `score_zone` (which includes risk rules); `feedback_score_*` settings, default **off** |
| Rationale `operator_feedback` factor | Appended in engine when adjustment non-zero |
| Docs | `INGEST_API.md` operator outcomes section |
| Tests | `test_outcome_feedback_service.py`, `test_outcomes_api.py`; engine path covered via zone adjustment test |
| SageMaker / auto-edit `risk_rules` | Out of scope per plan |

## Product brief

- **“Capture user outcomes and feed them back into model/risk-score refinement”** — capture via append-only rows + export `GET`; refinement via optional bounded prior (settings-gated). Full ML loop remains external.

## Issues found and fixes

### 1. `GET /outcomes` without `org_id` listed all org scopes (fixed)

Same class of issue as **`GET /issues`**: omitting `org_id` did not constrain `org_scope`, so export queries could mix tenant rows.

**Change:** When `org_id` is omitted, require **`org_scope == "global"`**.

**Test:** `test_list_without_org_id_returns_only_global_scope`.

### 2. `primary_detection_id` vs `target_inspection_id` (fixed)

A client could reference a detection from inspection **A** while claiming **`target_inspection_id`** for inspection **B**, producing inconsistent training anchors.

**Change:** When both are set, require **`Detection.inspection_id == target_inspection_id`** (422).

**Test:** `test_submit_primary_detection_must_match_target_inspection`.

## Notes (informational)

- **`list_outcome_feedback`** does not join `Detection` for `model_name` / `model_version` filters when those columns were denormalized at insert—filters use stored columns; plan allowed denormalized approach.
- **Zone feedback aggregation** when the zone has no defect/hazard detections omits `issue_key` filter and counts all directional outcomes for that zone + scope (documented in `INGEST_API.md`).
- **`PUT /issues/state`** does not auto-create outcomes (plan: explicit `POST /outcomes` or flag—v1 uses explicit POST only).

## Data / API

- JSON **snake_case**; no extra response wrappers.

## Tests

Full backend suite run after fixes: all passed.
