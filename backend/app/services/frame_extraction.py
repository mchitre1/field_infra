from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.frame import Frame
from app.models.inspection import Inspection, InspectionStatus
from app.services import storage

log = logging.getLogger(__name__)


@dataclass
class ExtractedFrame:
    """Normalized extracted frame payload used before persistence."""

    frame_index: int
    frame_timestamp_ms: int
    image_jpeg: bytes
    width: int
    height: int


def _extract_image_frame(raw: bytes) -> list[ExtractedFrame]:
    """Decode image bytes and normalize to a single JPEG frame."""
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return [
        ExtractedFrame(
            frame_index=0,
            frame_timestamp_ms=0,
            image_jpeg=buf.getvalue(),
            width=img.width,
            height=img.height,
        )
    ]


def _extract_video_frames(
    raw: bytes,
    *,
    fps: float,
    max_frames: int,
) -> tuple[list[ExtractedFrame], dict[str, int | float | str]]:
    """Sample video bytes into JPEG frames and return extraction summary fields."""
    try:
        import imageio.v3 as iio
    except Exception as exc:
        raise RuntimeError("Video frame extraction dependency unavailable") from exc

    if fps <= 0:
        fps = 1.0
    src = io.BytesIO(raw)
    props = iio.improps(src, plugin="pyav")
    src.seek(0)
    native_fps = float(props.fps or fps)
    step = max(1, int(round(native_fps / fps)))
    frames: list[ExtractedFrame] = []
    for i, arr in enumerate(iio.imiter(src, plugin="pyav")):
        if i % step != 0:
            continue
        if len(frames) >= max_frames:
            break
        image = Image.fromarray(arr).convert("RGB")
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=88)
        ts_ms = int((i / native_fps) * 1000)
        frames.append(
            ExtractedFrame(
                frame_index=len(frames),
                frame_timestamp_ms=ts_ms,
                image_jpeg=out.getvalue(),
                width=image.width,
                height=image.height,
            )
        )
    duration_ms = int((props.n_images / native_fps) * 1000) if props.n_images else None
    summary = {
        "video_duration_ms": duration_ms or 0,
        "video_fps": native_fps,
        "video_codec": "unknown",
    }
    return frames, summary


def extract_and_store_frames(
    *,
    settings: Settings,
    db: Session,
    s3_client: Any,
    inspection_id: uuid.UUID,
    extraction_hints: dict[str, str | int | float] | None = None,
) -> int:
    """Extract frames for one inspection and persist both artifacts and frame metadata rows.

    Returns the number of extracted frames. The function is idempotent for completed
    inspections (`frames_extracted` + existing rows) and marks failures as `frames_failed`.
    """
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise ValueError(f"Inspection {inspection_id} not found")

    existing = db.scalar(
        select(Frame.id).where(Frame.inspection_id == inspection_id).limit(1)
    )
    if existing and inspection.status == InspectionStatus.frames_extracted:
        return int(inspection.frame_count or 0)

    inspection.status = InspectionStatus.processing_frames
    db.add(inspection)
    db.commit()

    try:
        raw = storage.get_object_bytes(
            s3_client=s3_client, bucket=inspection.s3_bucket, key=inspection.s3_key
        )
        content_type = inspection.content_type or ""
        hints = extraction_hints or {}
        fps = float(hints.get("fps", settings.frame_extraction_fps))
        max_frames = int(hints.get("max_frames", settings.max_frames_per_inspection))
        frames_bucket = str(
            hints.get("frames_bucket") or settings.frames_bucket or settings.s3_bucket
        )

        if content_type.startswith("image/"):
            frames = _extract_image_frame(raw)
            video_summary: dict[str, int | float | str] = {}
        elif content_type.startswith("video/"):
            frames, video_summary = _extract_video_frames(
                raw, fps=fps, max_frames=max_frames
            )
        else:
            raise RuntimeError(f"Unsupported media type for extraction: {content_type}")

        db.execute(delete(Frame).where(Frame.inspection_id == inspection.id))
        for frame in frames:
            key = storage.build_frame_object_key(
                settings=settings,
                org_id=inspection.org_id,
                inspection_id=inspection.id,
                frame_index=frame.frame_index,
            )
            storage.put_bytes(
                settings=settings,
                s3_client=s3_client,
                bucket=frames_bucket,
                key=key,
                content=frame.image_jpeg,
                content_type="image/jpeg",
            )
            capture_ts = (
                inspection.capture_timestamp + timedelta(milliseconds=frame.frame_timestamp_ms)
                if inspection.capture_timestamp is not None
                else None
            )
            db.add(
                Frame(
                    id=uuid.uuid4(),
                    inspection_id=inspection.id,
                    frame_index=frame.frame_index,
                    frame_timestamp_ms=frame.frame_timestamp_ms,
                    s3_bucket=frames_bucket,
                    s3_key=key,
                    width=frame.width,
                    height=frame.height,
                    capture_timestamp=capture_ts,
                    latitude=inspection.latitude,
                    longitude=inspection.longitude,
                    source_type=inspection.source_type,
                    site_hint=inspection.site_hint,
                    asset_hint=inspection.asset_hint,
                )
            )

        inspection.frame_count = len(frames)
        inspection.status = InspectionStatus.frames_extracted
        if inspection.extra_metadata:
            inspection.extra_metadata = {
                k: v
                for k, v in inspection.extra_metadata.items()
                if k != "frame_extraction_error"
            }
        if video_summary:
            inspection.video_duration_ms = int(video_summary.get("video_duration_ms") or 0)
            inspection.video_fps = float(video_summary.get("video_fps") or 0)
            inspection.video_codec = str(video_summary.get("video_codec") or "unknown")
        db.add(inspection)
        db.commit()
        return len(frames)
    except Exception as exc:
        db.rollback()
        inspection = db.get(Inspection, inspection_id)
        if inspection is not None:
            inspection.status = InspectionStatus.frames_failed
            metadata = dict(inspection.extra_metadata or {})
            metadata["frame_extraction_error"] = str(exc)
            inspection.extra_metadata = metadata
            db.add(inspection)
            db.commit()
        log.exception("Frame extraction failed for inspection %s", inspection_id)
        raise
