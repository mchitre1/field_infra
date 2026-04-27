# Code review: Feature 0002 (frame extraction + frame metadata)

**Scope:** implementation vs `docs/features/0002_PLAN.md` and ingestion-related product brief requirements.  
**Artifacts reviewed:** `backend/app/**`, `backend/alembic/**`, `backend/tests/**`.  
**Validation run:** `python -m pytest -q` in `backend` — **18 passed**.

## Findings (by severity)

### High: video extraction path likely fails in production dependency set

`app/services/frame_extraction.py` uses `imageio.v3` with `plugin="pyav"` (`_extract_video_frames`), but `pyproject.toml` does not include `av`/`pyav` dependency. The installed `imageio-ffmpeg` package does not satisfy this plugin requirement.  
Result: video jobs can fail at runtime with `"Video frame extraction dependency unavailable"` and move inspections to `frames_failed`.

### High: worker ignores queue-provided `frames_bucket` hint

`app/jobs/publisher.py` includes `frame_extraction["frames_bucket"]`, but `app/services/frame_extraction.py` resolves output bucket only from `settings.frames_bucket or settings.s3_bucket`.  
This creates a data-contract mismatch between job payload and worker behavior and can write frames to an unexpected bucket when worker config differs from API config.

### Medium: no durable failure reason stored on inspection for frame failures

Plan calls for persisting error detail for observability on recoverable/unrecoverable failures. In `extract_and_store_frames`, failures set `status=frames_failed` but do not persist any error detail field/metadata update.  
This makes root-cause diagnosis and retry policy decisions harder without log access.

### Medium: frame listing endpoint has no guardrails on pagination inputs

`GET /ingest/{inspection_id}/frames` accepts unconstrained `limit`/`offset`. Negative values or excessively large `limit` are not validated.  
Risk: avoidable heavy queries and inconsistent pagination behavior.

### Low: FFmpeg/FFprobe settings added but currently unused

`ffmpeg_bin` and `ffprobe_bin` were added to config per plan, but extraction implementation does not use them (current path relies on Pillow + imageio plugin APIs).  
Not a blocker, but this diverges from the plan’s explicit tool-path configurability intent.

## Plan alignment snapshot

- **Implemented well:** frame model + migration, inspection frame summary/status fields, worker processing path, deterministic frame keys, context propagation (`source_type/site/asset/lat/lon`), list-frames API, and test coverage expansion.
- **Partial/missing vs plan:** explicit persisted failure reason, immutable use of message-provided processing context (notably `frames_bucket`), and dedicated `test_frame_extraction.py` file (coverage exists, but tests live in `test_ingest_service.py`).

## Open questions / assumptions

- Assumed the intended contract is: worker should honor extraction hints from the SQS payload when present.
- Assumed `frames_failed` states should include machine-readable reason in DB (field on `inspections` or metadata JSON).
- Assumed current idempotency policy (“clear and rebuild frames on rerun unless already `frames_extracted`”) is acceptable for v1.

## Summary

Feature 0002 is mostly in place and test-backed, but two correctness issues should be addressed before calling it production-ready:  
1) include the actual video extraction runtime dependency (or switch plugin path), and  
2) make the worker honor `frames_bucket` from the job contract.  
After that, add persisted failure detail and pagination bounds to tighten operability.
