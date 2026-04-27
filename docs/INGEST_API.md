# Ingestion API (feature 0001)

The ingestion layer accepts **images and video** with metadata, writes objects to **Amazon S3**, records each inspection in **PostgreSQL**, and sends a JSON job to **Amazon SQS** when `SQS_QUEUE_URL` is set. The HTTP API is **snake_case** in JSON; responses use the same field names as the SQLAlchemy models exposed via Pydantic.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness probe |
| `POST` | `/ingest/upload` | Multipart upload through the API |
| `POST` | `/ingest/presign` | Create inspection row + presigned `PUT` URL for direct S3 upload |
| `POST` | `/ingest/{inspection_id}/complete` | After client `PUT` to S3, verify object and finalize (`stored` + enqueue) |

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
| `failed` | Reserved enum value; not used by the current happy-path flows |

If `SQS_QUEUE_URL` is empty, successful uploads remain **`stored`** after persist (no queue).

## SQS message body

Messages are the JSON serialization of `IngestJobMessage`:

- `inspection_id` (UUID)
- `s3_uri` (e.g. `s3://bucket/org/.../file.mp4`)
- `content_type`
- `source_type` (string enum value, e.g. `"drone"`)
- `capture_timestamp`, `site_hint`, `asset_hint` (optional)
- `frame_extraction` — v1 placeholder object (`{"mode": "default"}`)

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

Allowed MIME types default to `image/jpeg`, `image/png`, `video/mp4`, `video/quicktime`. Override via settings if the project extends the allowlist.

## Worker stub

`python -m app.workers.ingest_ack` is a minimal CLI stub for local smoke tests; production workers would consume SQS and drive downstream processing.
