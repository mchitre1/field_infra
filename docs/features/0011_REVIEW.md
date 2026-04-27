# Feature 0011 — Code review (zone decision log + inspection history)

Reviewed against `docs/features/0011_PLAN.md`, `commands/code_review_05.md`, and `docs/PRODUCT_BRIEF.md` (traceable history per asset/zone + compliance/auditability).

## Plan coverage

| Plan item | Status |
|-----------|--------|
| Append-only `zone_decision_logs` with FKs + `payload` | `ZoneDecisionLog` model; migration `0010_add_zone_decision_and_inspection_history.py` |
| Separate `inspection_history_events` | `InspectionHistoryEvent` + `inspection_history_service` (`record_inspection_status_transition`, `list_inspection_history`) |
| `append_zone_decision_log` / `list_zone_decision_log` | `zone_decision_log_service.py`; `truncate_rationale_for_payload` for recommendation snapshots |
| Hooks: `issue_state_service`, `outcome_feedback_service`, `recommendation_engine` | After events / outcome insert / per recommendation row |
| Inspection history hooks in pipeline, alignment, ingest, publisher, frame extraction, detection | `record_inspection_status_transition` wired (per grep) |
| `GET /ingest/zone-decision-log`, `GET /ingest/inspection-history` | `ingest.py`; inspection history **404** if inspection missing |
| Schemas `decision_log.py` | `ZoneDecisionLogPublic`, list envelope; inspection history list |
| Tests | `test_zone_decision_log_service.py`, `test_zone_decision_log_hooks.py` |
| Docs + brief repository note | `INGEST_API.md`; `PRODUCT_BRIEF.md` already lists feature 0011 |
| Timeline not merged with decision log | Documented in `INGEST_API.md` |

## Plan alignment notes

- **Org column on logs:** Rows store nullable **`org_id`** (not `org_scope` string like `IssueState`). Listing semantics are documented alongside issues/outcomes.
- **Recommendation replace:** Each persisted recommendation row triggers a log append with denormalized **`payload.refs`** (including truncated rationale) so audit survives the next delete batch.

## Issue found and fix

### 1. `GET` zone decision log without `org_id` listed all tenants (fixed)

`list_zone_decision_log` treated a missing **`org_id`** as “no filter,” returning every org’s rows for that **`asset_zone_id`**, unlike **`GET /issues`** / **`GET /outcomes`** (global-only when `org_id` omitted).

**Change:** When **`org_id`** is omitted, constrain to **`ZoneDecisionLog.org_id IS NULL`** (global bucket). Pass **`org_id`** to list tenant-scoped log rows.

**Tests:** `test_append_and_list_zone_decision_log` now seeds one global row and asserts unscoped list returns only that row.

**Docs:** `INGEST_API.md` updated.

## Data / API

- Responses use **snake_case**; `payload` is a plain JSON object with `summary` + `refs` as implemented.

## Tests

Full backend suite run after the change; all tests passed.
