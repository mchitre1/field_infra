# Feature 0005 — Code review (progression metrics)

Reviewed implementation against `docs/features/0005_PLAN.md` and `commands/code_review_05.md`.

## Plan coverage

| Plan item | Status |
|-----------|--------|
| Config: `progression_min_time_delta_seconds`, `progression_crack_metric`, `progression_vegetation_metric` | Implemented in `app/core/config.py`. |
| `ProgressionMetric` model + FKs + indexes | Implemented; migration `0005_add_progression_metrics.py` matches composite indexes. |
| `progression_metric_count` on `Inspection` | Implemented; no new `InspectionStatus` values (plan allowed metadata-only policy). |
| Schemas + paginated list | `app/schemas/progression.py` + `PaginatedProgressionMetricsResponse`. |
| `progression.py` orchestration + crack/vegetation modules | Implemented; taxonomy via `CRACK_CLASSES` / `VEGETATION_ENCROACHMENT_CLASSES`. |
| Worker after alignment | `ingest_ack.py` calls `run_progression_for_inspection` after `run_alignment_for_inspection`. |
| `GET /ingest/{id}/progression` with filters + pagination | Implemented in `ingest.py`; ordering matches plan (`asset_zone_id`, `metric_name`, `created_at`). |
| `GET .../progression/summary` | Implemented (optional in plan). |
| Unit tests for math + service + API | `test_progression_metrics.py`, `test_progression_service.py`, `test_ingest_api.py`. |
| Idempotency: replace metrics per target | Delete-then-insert for `target_inspection_id`. |
| Eligibility: `alignment_ready` + `change_type == persisted` + both detection IDs | Query matches matcher output (`persisted` from `match_detection_sets`). |

## Issues found and resolution

### 1. Delete-before-gate (fixed)

Previously, `run_progression_for_inspection` executed `DELETE` from `progression_metrics` for the target inspection **before** verifying `inspection.status == alignment_ready`. Any call while the inspection was not `alignment_ready` (e.g. `alignment_failed` after a regression) would wipe existing metrics even though no recompute ran.

**Change:** Return early when status is not `alignment_ready`, and only then run delete + recompute. Aligns with the plan’s eligibility rule and avoids destroying audit data on failed alignment reruns.

### 2. Summary “latest_value” semantics (informational)

`summary` groups all rows per `metric_name` ordered by `created_at` and takes the last row as `latest_value`. That is “latest inserted row for that metric name globally,” not per `asset_zone_id`. Acceptable for v1; document if product needs per-zone summaries.

### 3. Duplicated `_ref_time` (informational)

`progression_crack.py` and `progression_vegetation.py` each define `_ref_time` matching `alignment` / inspection conventions. Small DRY opportunity only; not changed.

### 4. `progression_vegetation_metric` (informational)

v1 ignores non–`bbox_area` modes in `vegetation_area`, as documented in code and plan.

## Data shape / API consistency

- Responses use snake_case Pydantic models aligned with DB columns (`metric_name`, `asset_zone_id`, `alignment_pair_id`, etc.). No nested `{ data: ... }` wrapper on these routes.
- JSON `payload` stores numeric bbox keys as nested objects with string keys consistent with other services.

## Style and scope

- File sizes are moderate; no refactor required.
- Error handling mirrors alignment: `progression_error` in `extra_metadata` on failure paths that use `_record_progression_error`.

## Tests

Full backend suite re-run after the progression gate fix; all tests passed.
