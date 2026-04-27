# Feature 0009 — Code review (issue state)

Reviewed against `docs/features/0009_PLAN.md`, `commands/code_review_05.md`, and `docs/PRODUCT_BRIEF.md` (requirement: operator disposition without overwriting pipeline artifacts; auditability).

## Plan coverage

| Plan item | Status |
|-----------|--------|
| Stable identity `(org_scope, asset_zone_id, issue_key)` | `IssueState` + unique constraint; `org_scope` string (`str(org_id)` or `"global"`) avoids NULL-uniqueness pitfalls |
| States `fixed` \| `monitoring` \| `deferred` \| `ignored` | Enforced in service + Pydantic `IssueStateLiteral` |
| `notes`, `updated_by`, `last_target_inspection_id` | Persisted; FK to `inspections` with `SET NULL`; missing inspection → **404** on upsert |
| `IssueStateEvent` append-only | Implemented; create + transition-only (no duplicate event when `state` unchanged) |
| `issue_key.py` | `build_issue_key(detection_type, class_name, subtype=...)` |
| `issue_state_service` upsert + list | Implemented |
| `PUT /issues/state` with JSON body | Implemented; optional server-built key via `detection_type` + `class_name` + `subtype` |
| `GET /issues` filters + pagination + `include_events` | Implemented |
| `schemas/issues.py` | `IssueUpsertRequest`, `IssuePublic`, `IssueListResponse`, `IssueStateEventPublic` |
| Migration (plan label `0008_*`, chain `0007` → `0008`) | `0008_add_issue_states.py` after `0007` risk_rules |
| Tests: `test_issue_key`, `test_issue_state_service`, `test_issues_api` | Present |
| `maintenance_recommendation.issue_state_id` | Not added (plan optional defer) |
| Docs | `INGEST_API.md` issue section |

## Product brief alignment

- **“Allow users to update issue state”** — satisfied via `PUT /issues/state` and persisted rows.
- **“Continuous improvement loop / outcomes”** — explicitly out of scope in the plan; not implemented (no ML feedback).
- **“Auditability / traceability”** — `issue_state_events` provides append-only transitions; `context` column exists for future enrichment (currently null on write).

## Issues found and fixes

### 1. `GET /issues` without `org_id` listed all org buckets (fixed)

Previously, omitting `org_id` applied **no** `org_scope` filter, so any tenant row matching `asset_zone_id` / `state` could appear alongside global rows—awkward for multi-tenant dashboards and easy to misread.

**Change:** When `org_id` is omitted, constrain to **`org_scope == "global"`** only. Callers pass `org_id` to list tenant-scoped issues.

**Test:** `test_list_without_org_id_returns_only_global_scope`.

**Docs:** `INGEST_API.md` updated to describe the behavior.

## Minor notes (no code change)

- **`PUT /issues/state` response** always returns `events: []`; history is fetched via `GET /issues?include_events=true`. Acceptable for v1.
- **`IssueState` relationship** uses `cascade="all, delete-orphan"` on events—fine for ORM-managed children; events are not meant to be edited independently.

## Data / API shape

- JSON **snake_case** (`asset_zone_id`, `issue_key`, `last_target_inspection_id`, `from_state`, `to_state`).
- No extra `{ "data": ... }` wrappers on issue routes.

## Tests

Full backend suite: **86 passed** after the list-scope fix.
