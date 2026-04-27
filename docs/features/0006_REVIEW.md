# Feature 0006 — Code review (change maps, anomaly timelines, trend summaries)

Reviewed against `docs/features/0006_PLAN.md` and `commands/code_review_05.md`.

## Plan coverage

| Plan item | Status |
|-----------|--------|
| Schemas: change map, timeline entry, trend summary | `app/schemas/temporal_insights.py` |
| `change_map.py` — alignments + detections + frames, normalized bbox, optional presigns | Implemented; reuses `storage.generate_presigned_get` |
| `anomaly_timeline.py` — cohort filters, ChangeEvent + ProgressionMetric, `effective_at` precedence | Implemented; `asset_zone_id` required at API |
| `trend_summary.py` — series + aggregates | Implemented (see fixes below) |
| GET `/ingest/compare/change-map`, `/ingest/timeline`, `/ingest/trends` | On `ingest` router; `/timeline` requires `asset_zone_id` (422 if missing) |
| Config caps: timeline, trend, change map | `timeline_max_entries`, `trend_max_points`, `trend_min_span_days`, `change_map_max_features` |
| Tests: services + `test_ingest_api` | `test_change_map_service.py`, `test_anomaly_timeline_service.py`, `test_trend_summary_service.py`, API tests |
| `docs/INGEST_API.md` | Feature 0006 section present; updated for trend aggregates and progression gate |

## Issues found and fixes

### 1. Trend aggregates over truncated slice only (fixed)

The plan’s trend algorithm (§C) loads the full matching series for aggregates and `delta_first_to_latest` / slope. The implementation computed `min`/`max`/`mean`/`delta`/`slope` only over the **last** `trend_max_points` rows, so dashboards could mis-report when the series was longer than the cap.

**Fix:** Run SQL `MIN`/`MAX`/`AVG` over the full filtered join, and separate `ORDER BY effective_at … LIMIT 1` queries for chronologically first and last rows for delta/slope/latest. `points[]` remains the capped recent window; `truncated` still reflects whether `points` omits data.

**Test:** `test_trend_truncated_points_keeps_global_aggregates`.

### 2. Query parameter hygiene (fixed)

- `/ingest/timeline`: `site_hint` is stripped when provided (consistent with `asset_zone_id`).
- `/ingest/trends`: `metric_name` is stripped at the route (avoids leading/trailing whitespace mismatches).

### 3. Naming: `change_map_max_features` (informational)

Settings field name suggests drawable features, but the cap limits **alignment pair** rows processed (each pair may produce up to two `ChangeMapFeature` rows). `INGEST_API.md` already describes the cap as alignment pairs; renaming the env var would be breaking—left as documentation only.

### 4. Timeline merge cap (`cap = timeline_max_entries * 5`, max 50_000)

Heuristic to pull enough rows from each source before merge/sort/truncate. Reasonable guardrail; slightly opaque but acceptable for v1.

## Data alignment / API shape

- JSON remains **snake_case** (`effective_at`, `asset_zone_id`, `frame_image_url`, etc.).
- Change map `geometry` uses flat `xmin`/`ymin`/`xmax`/`ymax` (not GeoJSON) — documented for the React consumer in `INGEST_API.md`.
- Timeline `refs` embeds `payload` dicts from DB JSON; no extra `{ data: ... }` wrapper.

## Style and structure

- Services are small and focused; routes stay on `ingest.py` as allowed by the plan.
- No unnecessary refactors beyond the trend aggregate correction.

## Tests

Full backend suite: **58 passed** after changes.
