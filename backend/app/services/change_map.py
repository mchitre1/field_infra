"""Assemble normalized change-map features from alignment pairs and detections."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.alignment import Alignment
from app.models.detection import Detection, DetectionType
from app.models.frame import Frame
from app.models.inspection import Inspection
from app.schemas.temporal_insights import ChangeMapFeature, ChangeMapResponse, NormalizedBBoxGeometry
from app.services import storage


def _detection_type_label(dt: DetectionType | str) -> str:
    if isinstance(dt, DetectionType):
        return dt.value
    return str(dt)


def build_change_map(
    *,
    settings: Settings,
    db: Session,
    s3_client: Any,
    baseline_inspection_id: uuid.UUID,
    target_inspection_id: uuid.UUID,
    asset_zone_id: str | None,
    frame_id: uuid.UUID | None,
    include_frame_urls: bool,
) -> ChangeMapResponse:
    """Load alignment rows and emit one ChangeMapFeature per visible detection side."""
    if db.get(Inspection, baseline_inspection_id) is None or db.get(Inspection, target_inspection_id) is None:
        raise LookupError("inspection not found")

    base_filter = [
        Alignment.baseline_inspection_id == baseline_inspection_id,
        Alignment.target_inspection_id == target_inspection_id,
    ]
    if asset_zone_id is not None:
        base_filter.append(Alignment.asset_zone_id == asset_zone_id)

    total = db.scalar(select(func.count()).select_from(Alignment).where(*base_filter)) or 0
    lim = settings.change_map_max_features
    truncated = total > lim

    stmt = (
        select(Alignment)
        .where(*base_filter)
        .order_by(Alignment.created_at.desc(), Alignment.id.desc())
        .limit(lim)
    )
    pairs: list[Alignment] = list(db.scalars(stmt).all())
    pairs.reverse()

    det_ids: set[uuid.UUID] = set()
    for p in pairs:
        if p.baseline_detection_id is not None:
            det_ids.add(p.baseline_detection_id)
        if p.target_detection_id is not None:
            det_ids.add(p.target_detection_id)
    if not det_ids:
        return ChangeMapResponse(
            baseline_inspection_id=baseline_inspection_id,
            target_inspection_id=target_inspection_id,
            asset_zone_id=asset_zone_id,
            features=[],
            truncated=truncated,
        )

    dets = db.scalars(select(Detection).where(Detection.id.in_(det_ids))).all()
    det_by_id: dict[uuid.UUID, Detection] = {d.id: d for d in dets}

    frame_ids = {d.frame_id for d in dets}
    frames = db.scalars(select(Frame).where(Frame.id.in_(frame_ids))).all()
    frame_by_id: dict[uuid.UUID, Frame] = {f.id: f for f in frames}

    features: list[ChangeMapFeature] = []
    for p in pairs:
        for side, iid, did in (
            ("baseline", baseline_inspection_id, p.baseline_detection_id),
            ("target", target_inspection_id, p.target_detection_id),
        ):
            if did is None:
                continue
            det = det_by_id.get(did)
            if det is None:
                continue
            if frame_id is not None and det.frame_id != frame_id:
                continue
            fr = frame_by_id.get(det.frame_id)
            url: str | None = None
            if include_frame_urls and fr is not None:
                url = storage.generate_presigned_get(
                    settings=settings,
                    s3_client=s3_client,
                    bucket=fr.s3_bucket,
                    key=fr.s3_key,
                )
            features.append(
                ChangeMapFeature(
                    alignment_pair_id=p.id,
                    side=side,  # type: ignore[arg-type]
                    change_type=p.change_type,
                    alignment_score=p.alignment_score,
                    class_name=det.class_name,
                    detection_type=_detection_type_label(det.detection_type),
                    detection_id=det.id,
                    frame_id=det.frame_id,
                    inspection_id=iid,
                    geometry=NormalizedBBoxGeometry(
                        xmin=det.bbox_xmin,
                        ymin=det.bbox_ymin,
                        xmax=det.bbox_xmax,
                        ymax=det.bbox_ymax,
                    ),
                    frame_width=fr.width if fr else None,
                    frame_height=fr.height if fr else None,
                    frame_image_url=url,
                )
            )

    return ChangeMapResponse(
        baseline_inspection_id=baseline_inspection_id,
        target_inspection_id=target_inspection_id,
        asset_zone_id=asset_zone_id,
        features=features,
        truncated=truncated,
    )
