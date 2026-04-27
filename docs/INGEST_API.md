# Ingestion, Frame Extraction, and Detection API (features 0001-0003)

The ingestion layer accepts **images and video** with metadata, writes source objects to **Amazon S3**, records inspections in **PostgreSQL**, and sends a JSON job to **Amazon SQS** when `SQS_QUEUE_URL` is set.

Feature 0002 extends this flow with worker-side frame extraction: frame JPEG artifacts are stored in S3 and frame-level metadata is persisted in PostgreSQL.

Feature 0003 adds frame-level detection/classification: detections are persisted with confidence, bounding boxes, optional geometry/attributes, and grouped as `asset`, `defect`, or `environmental_hazard`.

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
| `failed` | Reserved enum value; not used by the current happy-path flows |

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

## Worker flow (frame extraction + detection)

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

On extraction failure, status is `frames_failed` and error is stored in `inspection.metadata.frame_extraction_error`.
On detection failure, status is `detections_failed` and error is stored in `inspection.metadata.detection_error`.

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

Allowed MIME types default to `image/jpeg`, `image/png`, `video/mp4`, `video/quicktime`. Override via settings if the project extends the allowlist.

## Worker invocation note

`app.workers.ingest_ack` is currently a payload-driven CLI entrypoint. It executes extraction when called with a JSON message body and can be wrapped by SQS consumer infrastructure.
