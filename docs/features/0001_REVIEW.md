# Code review: Feature 0001 (ingest video/images)

**Scope:** Implementation vs [0001_PLAN.md](0001_PLAN.md) and [PRODUCT_BRIEF.md](../PRODUCT_BRIEF.md) ingestion slice.  
**Artifacts reviewed:** `backend/app/**`, `backend/alembic/**`, `backend/tests/**`.  
**Tests:** `python -m pytest` in `backend` — 9 passed.

---

## Verdict

The vertical slice is **largely aligned** with the plan: FastAPI ingestion API, PostgreSQL inspection rows, S3 storage, SQS publish with failure handling (`stored_pending_queue`), presigned PUT flow, Alembic migration, structured logging with correlation IDs, and tests for happy path, MIME rejection, size limit, presign/complete, and publisher behavior.

Remaining gaps are mostly **small correctness/ops edges**, one **ordering bug** in the presign path, and a **plan checklist item** (global request size limit) that is only partially met.

---

## Plan coverage checklist

| Plan item | Status |
|-----------|--------|
| `main.py` — app factory, middleware, routers | **Partial** — correlation ID middleware and `/health` present; no global request body size limit middleware (see findings). |
| `core/config.py` — S3, DB, SQS, max upload, MIME allowlist, KMS | **Met** (`presign_expires_seconds` added; reasonable). |
| `core/logging.py` — structured logging | **Met** — stdout, level, correlation id on records. |
| `api/routes/ingest.py`, `api/deps.py` | **Met** |
| `schemas/ingest.py` | **Met** |
| `models/inspection.py` + Alembic | **Met** — lat/lon as floats; no PostGIS geometry (plan marked optional). |
| `services/storage.py`, `services/ingest.py` | **Met** |
| `jobs/messages.py`, `jobs/publisher.py` | **Met** |
| `workers/ingest_ack.py` stub | **Met** |
| Tests — API + service | **Met** — idempotency header / duplicate policy not tested (plan: optional). |
| IaC (Terraform/CDK) | **N/A** — not in repo; plan allows env-only wiring. |

---

## Issues and risks

### 1. Presign: DB commit before presigned URL generation (bug)

In `create_presigned_ingest`, the inspection row is **`commit`ted before** `storage.generate_presigned_put`. If `generate_presigned_url` fails (misconfiguration, client error, transient AWS), the API can error while leaving a **`received`** row with no way for the client to complete upload, and no URL returned.

**Suggestion:** Generate the presigned URL first, or commit only after a successful presign, or roll back / mark `failed` on presign failure.

### 2. Complete (presigned): S3 `ContentType` not verified

`complete_presigned_ingest` uses `head_object` for size (and existence) but does not compare **`ContentType`** from S3 to the stored `inspection.content_type`. A client can PUT bytes with a mismatched content type; only optional `expected_content_type` in the body is checked against the **DB** value, not S3 metadata.

**Suggestion:** Compare `head.get("ContentType")` to `inspection.content_type` (with normalization for charset suffixes) when HEAD returns it.

### 3. SQS publish: only `ClientError` is handled

`publish_ingest_job` catches `botocore.exceptions.ClientError` on `send_message`. Other exceptions (e.g. programming errors, unexpected SDK errors) will **propagate** after the row is already **`stored`**, leaving status inconsistent with “enqueue attempted” (neither `queued` nor `stored_pending_queue`).

**Suggestion:** Broaden handling or ensure the outer API layer maps failures to a consistent status and logs `inspection.id`.

### 4. Multipart: S3 success then DB failure → orphan object

If `put_fileobj` succeeds but `db.commit()` fails, the object remains in S3 without a committed row (no cleanup). The plan allowed choosing failure policy; this is an **operational** gap worth documenting or addressing with a compensating delete or a `failed` row in a single workflow.

### 5. Plan: “request size” middleware

The plan lists **request size** next to correlation ID on `main.py`. Upload size is enforced by **spooling** in `spool_upload_limited`, not by Starlette/FastAPI body limit middleware. That is sufficient for the multipart path but does not cap other large bodies globally.

**Suggestion:** If product requirements need it, add `Request`/`Middleware` limits or document that only ingest paths are capped.

### 6. Upload path: buffer-then-put vs stream

The multipart flow **buffers** the full upload (up to `max_upload_bytes`) then calls `upload_fileobj`. The plan described streaming to S3; behavior is correct for caps and simplicity but uses more temporary disk/memory than a true streaming pipeline for large allowed sizes.

---

## Data shape / API contract notes

- **JSON field names** are **snake_case** end-to-end (HTTP JSON, SQS `model_dump_json()`). Any downstream service expecting **camelCase** or a wrapper like `{"data": {...}}` would need a translation layer.
- **`InspectionPublic.status`** is a **string**; values match enum names (`queued`, `stored_pending_queue`, etc.). Consistent for OpenAPI clients.
- **`IngestJobMessage.source_type`** serializes as the string value (e.g. `"drone"`), not an object — verified via `model_dump_json()`.
- **Duplicate `SourceType` definitions:** `SourceTypeSchema` in `schemas/ingest.py` vs `SourceType` on the SQLAlchemy model — intentional layering, but keep them in sync when adding sources.

---

## Code quality and consistency

- **Size / complexity:** Modules are appropriately scoped; no file is unreasonably large.
- **Style:** Matches common FastAPI + SQLAlchemy 2 patterns; `Annotated` deps are consistent.
- **Async:** `upload_inspection` is `async`; presign/complete are sync — acceptable, minor inconsistency only.
- **Typing:** `S3Client` / `SQSClient` typed as `object` in deps — loose but avoids circular typing; could use `TYPE_CHECKING` + protocols later if desired.

---

## Testing observations

- Good coverage of MIME rejection, oversize multipart, correlation header, presign+complete, and publisher branches (including SQS failure).
- **Gaps (optional enhancements):** S3 failure on multipart → 502; presign failure after commit; `complete` with missing object (404); content-type mismatch with S3 HEAD.

---

## Summary

Ship-quality for a first slice: core flows match the plan and product brief’s ingestion layer. **Fix or harden the presign commit order** before treating presigned uploads as production-ready; tighten **S3 HEAD content-type** validation and **SQS error handling** for cleaner operational semantics.

---

## Fixes applied (implementation follow-up)

The following items from **Issues and risks** were addressed in code:

1. **Presign ordering** — `generate_presigned_put` runs before the inspection row is committed; presign failures return 502 with no persisted row.
2. **S3 `ContentType` on complete** — HEAD metadata is required and compared to the inspection record (with `;charset` stripped, case-insensitive MIME).
3. **SQS publish errors** — `publish_ingest_job` treats any exception from `send_message` like a queue failure (`stored_pending_queue` + `last_queue_error`).
4. **Multipart DB failure after S3** — On `commit` failure after a successful put, the code attempts `delete_object` best-effort and returns 500.
5. **Request body size** — Middleware rejects `POST`/`PUT`/`PATCH` when `Content-Length` exceeds `max_upload_bytes`; registered **before** correlation middleware so 413 responses still get `X-Request-ID`.

**Deferred:** Buffer-then-put vs true streaming (issue 6) — unchanged by design for v1.

**Validation:** `python -m pytest` in `backend` — 15 tests passing.
