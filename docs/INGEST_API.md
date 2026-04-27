# Ingestion through temporal insights API (features 0001-0006)

The ingestion layer accepts **images and video** with metadata, writes source objects to **Amazon S3**, records inspections in **PostgreSQL**, and sends a JSON job to **Amazon SQS** when `SQS_QUEUE_URL` is set.

Feature 0002 extends this flow with worker-side frame extraction: frame JPEG artifacts are stored in S3 and frame-level metadata is persisted in PostgreSQL.

Feature 0003 adds frame-level detection/classification: detections are persisted with confidence, bounding boxes, optional geometry/attributes, and grouped as `asset`, `defect`, or `environmental_hazard`.

Feature 0004 adds temporal alignment/change tracking: detection sets are aligned against a baseline inspection in the same cohort, aligned pairs are persisted, and change events are recorded for appeared/disappeared items.

Feature 0005 adds progression metrics: for each `persisted` alignment pair with both detection IDs set, the worker may emit crack and vegetation metrics (size/area deltas and optional per-day rates), persist rows in `progression_metrics`, and update `progression_metric_count` on the target inspection. Inspection **status** remains `alignment_ready` when progression succeeds; failures set `metadata.progression_error` and `progression_metric_count` to `0`.

Feature 0006 adds **read-only temporal insights** assembled from existing rows (no new pipeline stage): **change maps** (normalized bbox features for overlays), **anomaly timelines** (change events + progression metrics in one time-ordered list), and **trend summaries** (cross-inspection progression aggregates for an `asset_zone_id` + `metric_name`). Limits: `change_map_max_features`, `timeline_max_entries`, `trend_max_points` (see settings).

The HTTP API is **snake_case** in JSON; responses use Pydantic models mapped from SQLAlchemy rows.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness probe |
| `POST` | `/ingest/upload` | Multipart upload through the API |
| `POST` | `/ingest/presign` | Create inspection row + presigned `PUT` URL for direct S3 upload |
| `POST` | `/ingest/{inspection_id}/complete` | After client `PUT` to S3, verify object and finalize (`stored` + enqueue) |
| `GET` | `/ingest/{inspection_id}/frames` | List extracted frame metadata rows for an inspection |
| `GET` | `/ingest/{inspection_id}/detections` | List detections for an inspection with filtering + pagination |
| `GET` | `/ingest/{inspection_id}/frames/{frame_id}/detections` | List detections for a single frame |
| `GET` | `/ingest/{inspection_id}/alignment` | List alignment pairs for an inspection with filtering + pagination |
| `GET` | `/ingest/{inspection_id}/changes` | List change events for an inspection with filtering + pagination |
| `GET` | `/ingest/{inspection_id}/progression` | List progression metrics for a target inspection (filters + pagination) |
| `GET` | `/ingest/{inspection_id}/progression/summary` | Aggregate min/max/latest per `metric_name` for that inspection |
| `GET` | `/ingest/compare/change-map` | Normalized bbox features per alignment side for baseline vs target (optional frame presigns) |
| `GET` | `/ingest/compare/alignment` | Pairwise alignment rows between two inspections (baseline vs target) with filters + pagination |
| `GET` | `/ingest/timeline` | Unified timeline: `change_event` + `progression_metric` rows for an `asset_zone_id` |
| `GET` | `/ingest/trends` | Progression series + aggregates for one `asset_zone_id` and `metric_name` across inspections |

Correlation: send `X-Request-ID` or `X-Correlation-ID`; the response echoes `X-Request-ID`. Logs include the correlation id.

Request size: `POST`/`PUT`/`PATCH` requests with `Content-Length` greater than `max_upload_bytes` receive **413**. Multipart uploads are also capped while reading the file body.

## Multipart upload

`source_type` must be one of: `drone`, `mobile`, `fixed_camera`.

**Example** (curl):

```bash
curl -sS -X POST "http://127.0.0.1:8000/ingest/upload" \
  -H "X-Request-ID: demo-1" \
  -F "source_type=drone" \
  -F "site_hint=line-42" \
  -F "file=@./sample.jpg;type=image/jpeg"
```

Optional form fields: `org_id` (UUID), `asset_hint`, `capture_timestamp` (datetime), `latitude`, `longitude`.

Flow: validate content type against the allowlist → stream upload into a bounded buffer → `PUT` to S3 → insert row as `stored` → publish SQS message (or set `stored_pending_queue` on publish failure).

## Presigned upload

**1. Request a URL**

```bash
curl -sS -X POST "http://127.0.0.1:8000/ingest/presign" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "mobile",
    "content_type": "video/mp4",
    "filename": "tower.mp4",
    "site_hint": "substation-A"
  }'
```

Response includes `inspection_id`, `upload_url`, `s3_key`, and `headers` (e.g. `Content-Type`, KMS headers when `kms_key_id` is set). The inspection row starts in status **`received`** with `byte_size` null until completion.

**2. Upload to S3**

`PUT` the file bytes to `upload_url` using the returned headers.

**3. Complete**

```bash
curl -sS -X POST "http://127.0.0.1:8000/ingest/<inspection_id>/complete" \
  -H "Content-Type: application/json" \
  -d '{"expected_content_type": "video/mp4"}'
```

`expected_content_type` is optional; when provided it must match the inspection record. The server **HeadObject**s the key, requires `ContentType` metadata on the object, checks it matches the inspection (normalizing parameters such as `; charset=`), enforces max size, then sets `stored` and enqueues.

## Inspection status values

| Status | Meaning |
|--------|---------|
| `received` | Presign created; object not yet verified |
| `stored` | Bytes in S3 and DB row finalized (multipart immediately after S3 put; presign after complete) |
| `queued` | SQS message sent successfully |
| `stored_pending_queue` | Stored in S3/DB but SQS publish failed; `last_queue_error` may be set |
| `processing_frames` | Worker started frame extraction for this inspection |
| `frames_extracted` | Frame extraction finished and frame metadata is available |
| `frames_failed` | Frame extraction failed; see `metadata.frame_extraction_error` |
| `processing_detections` | Worker started detection/classification pass |
| `detections_ready` | Detection persistence completed for the inspection |
| `detections_failed` | Detection pass failed; see `metadata.detection_error` |
| `processing_alignment` | Worker started temporal alignment for this inspection |
| `alignment_ready` | Alignment pairs and change events persisted (or no baseline available) |
| `alignment_failed` | Alignment stage failed; see `metadata.alignment_error` |
| `failed` | Reserved enum value; not used by the current happy-path flows |

There are **no** separate `processing_progression` / `progression_ready` statuses: progression runs in the worker after alignment; use `progression_metric_count` and `metadata.progression_error` for outcomes.

If `SQS_QUEUE_URL` is empty, successful uploads remain **`stored`** after persist (no queue).

## SQS message body

Messages are the JSON serialization of `IngestJobMessage`:

- `inspection_id` (UUID)
- `s3_uri` (e.g. `s3://bucket/org/.../file.mp4`)
- `content_type`
- `source_type` (string enum value, e.g. `"drone"`)
- `capture_timestamp`, `site_hint`, `asset_hint` (optional)
- `frame_extraction` — extraction hints object, currently:
  - `mode` (default `default`)
  - `fps` (sampling target, default from `frame_extraction_fps`)
  - `max_frames` (guardrail, default from `max_frames_per_inspection`)
  - `frames_bucket` (resolved output bucket for frame artifacts)
- `detection` — detection hints object, currently:
  - `mode` (default `default`)
  - `threshold` (default from `inference_confidence_threshold`)
  - `model_name` / `model_version`
  - `enabled_classes` (empty list means no class allowlist)

## Worker flow (extraction + detection + alignment + progression)

The worker entrypoint is `python -m app.workers.ingest_ack '<json payload>'`.

Current behavior:

1. Parse `IngestJobMessage` and load the target inspection.
2. Set inspection status to `processing_frames`.
3. Read source bytes from `s3://{inspection.s3_bucket}/{inspection.s3_key}`.
4. Extract frames:
   - images: single frame (`frame_index=0`, `frame_timestamp_ms=0`)
   - videos: sampled by configured/queued FPS with `max_frames` cap
5. For each frame:
   - upload JPEG to S3 with deterministic key `{prefix}/{org}/{inspection_id}/frames/{frame_index:06d}.jpg`
   - persist frame metadata row (`frame_timestamp_ms`, dimensions, capture timestamp, location/source context)
6. Update inspection summary fields (`frame_count`, optional `video_duration_ms`, `video_fps`) and set status `frames_extracted`.
7. Run detection pipeline over extracted frames:
   - load each frame object from S3
   - run inference
   - apply threshold and optional `enabled_classes` filtering
   - persist detections with bbox, geometry, and model metadata
8. Update `detection_count` and set status `detections_ready`.
9. Run temporal alignment for the target inspection:
   - select a baseline inspection in same org/site/asset cohort
   - group detections by derived `asset_zone_id`
   - match baseline vs target detections (type/class + IoU threshold + confidence gate)
   - persist `alignment_pairs` and derived `change_events`
10. Update `aligned_pair_count`, `change_event_count`, and set status `alignment_ready`.
11. Run progression for the same target inspection when status is `alignment_ready`:
    - if status is not `alignment_ready`, progression skips without deleting existing metrics; otherwise delete existing `progression_metrics` rows for that target, then recompute
    - consider only alignment pairs with `change_type=persisted` and both `baseline_detection_id` and `target_detection_id` set
    - **Crack:** both detections are `defect` with class `crack` — emits `crack_size_delta` (always) and `crack_growth_rate` (only if elapsed time between inspections ≥ `progression_min_time_delta_seconds`)
    - **Vegetation:** both detections are `environmental_hazard` with class `vegetation_encroachment` — emits `vegetation_encroachment_delta` and optionally `vegetation_encroachment_rate` under the same time rule
    - elapsed time uses each inspection’s `capture_timestamp` when set, otherwise `created_at`
    - crack size proxy is controlled by `progression_crack_metric` (`bbox_width` \| `bbox_area` \| `max_extent`); vegetation v1 uses normalized bbox area only
12. Set `progression_metric_count` to the number of metric rows written (may be `0` if no eligible pairs).

On extraction failure, status is `frames_failed` and error is stored in `inspection.metadata.frame_extraction_error`.
On detection failure, status is `detections_failed` and error is stored in `inspection.metadata.detection_error`.
On alignment failure, status is `alignment_failed` and error is stored in `inspection.metadata.alignment_error`.
If progression fails after alignment, `metadata.progression_error` is set and `progression_metric_count` is cleared to `0`; inspection status is **not** changed by progression (it stays `alignment_ready` unless alignment itself failed earlier).

## Frame listing endpoint

`GET /ingest/{inspection_id}/frames` returns ordered frame metadata for one inspection.

Query params:

- `limit` (default `100`, min `1`, max `1000`)
- `offset` (default `0`, min `0`)

Example:

```bash
curl -sS "http://127.0.0.1:8000/ingest/<inspection_id>/frames?limit=50&offset=0"
```

## Detection listing endpoints

`GET /ingest/{inspection_id}/detections` returns a paginated response envelope:

- `items`: list of detections
- `total`: matching row count before pagination
- `limit`, `offset`: echo request pagination params

Supported filters:

- `detection_type` (`asset`, `defect`, `environmental_hazard`)
- `class_name` (case-insensitive exact match)
- `min_confidence` (`0.0`-`1.0`)
- `frame_id` (UUID)

Example:

```bash
curl -sS "http://127.0.0.1:8000/ingest/<inspection_id>/detections?detection_type=defect&min_confidence=0.5&limit=25&offset=0"
```

`GET /ingest/{inspection_id}/frames/{frame_id}/detections` returns the same paginated envelope scoped to one frame.

## Alignment and change endpoints

`GET /ingest/{inspection_id}/alignment` returns a paginated alignment-pair envelope:

- `items`: alignment rows
- `total`: matching row count
- `limit`, `offset`: pagination echo

Supported filters:

- `asset_zone_id`
- `change_type` (e.g. `persisted`, `appeared`, `disappeared`)

`GET /ingest/{inspection_id}/changes` returns paginated change events for the inspection with optional `event_type` filtering.

Example:

```bash
curl -sS "http://127.0.0.1:8000/ingest/<inspection_id>/alignment?change_type=appeared&limit=50&offset=0"
```

## Progression metrics endpoints

`GET /ingest/{inspection_id}/progression` returns a paginated envelope (`items`, `total`, `limit`, `offset`). Rows are ordered by `asset_zone_id`, `metric_name`, `created_at`.

Filters:

- `metric_name` (exact match after trim)
- `asset_zone_id`

Example:

```bash
curl -sS "http://127.0.0.1:8000/ingest/<inspection_id>/progression?metric_name=crack_growth_rate&limit=50&offset=0"
```

`GET /ingest/{inspection_id}/progression/summary` returns `target_inspection_id` and `items[]` with per-`metric_name` aggregates: `min_value`, `max_value`, `latest_value` (last row in creation order), and `count`.

## Temporal insights (feature 0006)

**Coordinate system (change map):** Each feature’s `geometry` uses **normalized image coordinates** (`xmin`, `ymin`, `xmax`, `ymax` in 0–1), matching persisted detection bboxes. Optional `frame_image_url` is a presigned **GET** for the underlying frame JPEG when `include_frame_urls=true`.

**Effective time (timeline + trends):** `effective_at` for timeline entries and trend `points` uses `coalesce(inspection.capture_timestamp, inspection.created_at)` on the **target** inspection row (`ChangeEvent.inspection_id` or `ProgressionMetric.target_inspection_id`).

### `GET /ingest/compare/change-map`

Query: `baseline_inspection_id`, `target_inspection_id` (required UUIDs); optional `asset_zone_id`, `frame_id` (restrict to one frame’s detections on each side), `include_frame_urls` (default `false`). Returns `features[]` (one entry per visible detection side: `baseline` and/or `target`), `truncated` if more than `change_map_max_features` alignment pairs matched (newest pairs kept).

### `GET /ingest/timeline`

Query: **`asset_zone_id`** (required); optional `org_id`, `site_hint` (exact match on `Inspection.site_hint`), `effective_from`, `effective_to` (filter on effective time), `event_type`, `metric_name`. Returns a JSON array of `TimelineEntry` objects sorted ascending by `effective_at`, then inspection and id tie-breakers. If the merged stream exceeds `timeline_max_entries`, the **oldest** entries are dropped so the response keeps the newest slice.

### `GET /ingest/trends`

Query: **`asset_zone_id`**, **`metric_name`** (required); optional `org_id`, `effective_from`, `effective_to`. Returns `points[]` in ascending `effective_at` order (at most `trend_max_points`, **most recent** samples when the series is longer). Aggregates `min_value`, `max_value`, `mean_value`, `latest_value`, `delta_first_to_latest`, and `simple_slope_per_day` are computed from the **full** filtered series (all matching rows), not only the returned `points` slice; `truncated` is true when `points` omits older samples.

### `GET /ingest/compare/alignment`

Query: `baseline_inspection_id`, `target_inspection_id` (required); optional `asset_zone_id`, `change_type`, `detection_type`, `class_name` (filters via joined detections where applicable), `limit`, `offset`. Returns `items` (alignment pair rows), `total`, and pagination echo—same row shape as single-inspection alignment list, scoped to one baseline/target pair.

**Examples**

```bash
# Change map (optional presigned frame JPEG URLs for overlay clients)
curl -sS "http://127.0.0.1:8000/ingest/compare/change-map?baseline_inspection_id=<uuid>&target_inspection_id=<uuid>&include_frame_urls=true"

# Timeline (asset_zone_id required)
curl -sS "http://127.0.0.1:8000/ingest/timeline?asset_zone_id=substation-a%3Acrack%3A4%3A5&org_id=<uuid>&effective_from=2026-01-01T00:00:00Z"

# Trends
curl -sS "http://127.0.0.1:8000/ingest/trends?asset_zone_id=substation-a%3Acrack%3A4%3A5&metric_name=crack_growth_rate"
```

`TimelineEntry.entry_kind` is either `change_event` or `progression_metric`; drill-down ids live under `refs` (e.g. `change_event_id`, `progression_metric_id`).

## Configuration

Environment variables are loaded via `pydantic-settings` (optional `.env` in the working directory). Common settings:

| Variable | Role |
|----------|------|
| `DATABASE_URL` | SQLAlchemy URL (default in code uses `postgresql+psycopg2://...`) |
| `AWS_REGION` | Boto3 region |
| `S3_BUCKET` | Target bucket (required for ingest; unset returns 503 on ingest routes) |
| `S3_KEY_PREFIX` | Optional key prefix for all objects |
| `SQS_QUEUE_URL` | Queue URL; omit to skip enqueue |
| `KMS_KEY_ID` | Optional; enables SSE-KMS on puts and presigned puts |
| `MAX_UPLOAD_BYTES` | Cap for uploads and `Content-Length` guard (default 100 MiB) |
| `PRESIGN_EXPIRES_SECONDS` | Presigned URL lifetime (default 3600) |
| `FRAMES_BUCKET` | Optional S3 bucket for extracted frames (falls back to `S3_BUCKET`) |
| `FRAME_EXTRACTION_FPS` | Default video frame sampling rate for worker jobs (default `1.0`) |
| `MAX_FRAMES_PER_INSPECTION` | Upper bound for extracted frames per inspection (default `300`) |
| `FFMPEG_BIN` / `FFPROBE_BIN` | Reserved tool path settings for extraction pipeline wiring |
| `INFERENCE_MODEL_NAME` | Detection model name persisted on detection rows (default `yolo`) |
| `INFERENCE_MODEL_VERSION` | Detection model version persisted on detection rows (default `v1`) |
| `INFERENCE_CONFIDENCE_THRESHOLD` | Default minimum confidence for inference outputs (default `0.35`) |
| `INFERENCE_DEVICE` | Inference runtime hint stored in detection attributes (default `cpu`) |
| `INFERENCE_BATCH_SIZE` | Reserved inference batching setting for runtime implementations |
| `SAM_MODEL_NAME` | Optional segmentation model hint for future geometry refinement |
| `ALIGNMENT_TIME_TOLERANCE_SECONDS` | Baseline-selection time tolerance window (default `86400`) |
| `ALIGNMENT_GEO_TOLERANCE_METERS` | Reserved geospatial tolerance setting for matching policies |
| `ALIGNMENT_IOU_THRESHOLD` | Minimum IoU for baseline/target detection matching (default `0.3`) |
| `ALIGNMENT_MIN_CONFIDENCE` | Confidence floor used by alignment matching (default `0.35`) |
| `ALIGNMENT_MAX_CENTROID_NORM_DISTANCE` | Max normalized image-space centroid distance for a candidate match (default `0.55`) |
| `PROGRESSION_MIN_TIME_DELTA_SECONDS` | Minimum seconds between baseline/target ref times before emitting `*_rate` metrics (default `3600`) |
| `PROGRESSION_CRACK_METRIC` | Crack size proxy: `bbox_width` \| `bbox_area` \| `max_extent` (default `bbox_width`) |
| `PROGRESSION_VEGETATION_METRIC` | Reserved; v1 always uses normalized bbox area for vegetation metrics |
| `TIMELINE_MAX_ENTRIES` | Cap on unified `/ingest/timeline` rows returned (default `2000`) |
| `TREND_MAX_POINTS` | Cap on `/ingest/trends` series length (default `500`) |
| `TREND_MIN_SPAN_DAYS` | Minimum day span before `simple_slope_per_day` is set (default `1.0`) |
| `CHANGE_MAP_MAX_FEATURES` | Max alignment pairs processed per `/ingest/compare/change-map` (default `5000`) |

Allowed MIME types default to `image/jpeg`, `image/png`, `video/mp4`, `video/quicktime`. Override via settings if the project extends the allowlist.

## Worker invocation note

`app.workers.ingest_ack` is a payload-driven CLI entrypoint. With a JSON job body it runs extraction, detection, alignment, and progression in one session and can be wrapped by SQS consumer infrastructure.
