"""Submit and list operator outcome feedback; zone-level score priors for recommendations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.detection import Detection, DetectionType
from app.models.inspection import Inspection
from app.models.issue_state import IssueState, IssueStateEvent
from app.models.maintenance_recommendation import MaintenanceRecommendation
from app.models.outcome_feedback import OutcomeFeedback
from app.schemas.outcomes import OutcomeSubmitRequest
from app.services.issue_key import build_issue_key
from app.services.issue_state_service import org_scope_for
from app.services.zone_decision_log_service import append_zone_decision_log


ALLOWED_CODES_BY_KIND: dict[str, frozenset[str]] = {
    "model_label": frozenset(
        {
            "false_positive",
            "false_negative",
            "severity_understated",
            "severity_overstated",
            "confirmed",
            "other",
        }
    ),
    "risk_priority": frozenset({"priority_too_high", "priority_too_low", "confirmed", "other"}),
    "general": frozenset({"confirmed", "other"}),
}


def _resolve_issue_key(body: OutcomeSubmitRequest) -> str:
    if body.issue_key and body.issue_key.strip():
        return body.issue_key.strip()
    if (
        body.detection_type
        and body.detection_type.strip()
        and body.class_name
        and body.class_name.strip()
    ):
        return build_issue_key(body.detection_type, body.class_name, subtype=body.subtype)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Provide issue_key or both detection_type and class_name",
    )


def _signal_direction(outcome_kind: str, outcome_code: str) -> int | None:
    """Map to score adjustment direction: -1 lower priority, +1 raise, None ignore for prior."""
    code = outcome_code.strip().lower()
    kind = outcome_kind.strip().lower()
    if kind == "risk_priority":
        if code == "priority_too_high":
            return -1
        if code == "priority_too_low":
            return +1
        return None
    if kind == "model_label":
        if code in ("false_positive", "severity_overstated"):
            return -1
        if code in ("false_negative", "severity_understated"):
            return +1
        return None
    return None


def _zone_issue_keys(detections: Sequence[Detection]) -> set[str]:
    keys: set[str] = set()
    for d in detections:
        if d.detection_type in (DetectionType.defect, DetectionType.environmental_hazard):
            keys.add(build_issue_key(d.detection_type.value, d.class_name))
    return keys


def zone_feedback_score_adjustment(
    *,
    db: Session,
    settings: Settings,
    inspection: Inspection,
    zone_id: str,
    zone_detections: Sequence[Detection],
) -> tuple[float, list[dict[str, Any]]]:
    """Bounded additive adjustment applied **after** persisted risk rules (see INGEST_API).

    Aggregates append-only outcomes in ``feedback_score_lookback_days`` for matching
    ``org_scope``, ``asset_zone_id``, and any ``issue_key`` derived from defect/hazard
    detections in this zone on the current scoring pass.
    """
    if not settings.feedback_score_enabled:
        return 0.0, []
    scope = org_scope_for(inspection.org_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(settings.feedback_score_lookback_days))
    keys = _zone_issue_keys(zone_detections)
    stmt = select(OutcomeFeedback.outcome_kind, OutcomeFeedback.outcome_code, func.count()).where(
        OutcomeFeedback.org_scope == scope,
        OutcomeFeedback.asset_zone_id == zone_id.strip(),
        OutcomeFeedback.created_at >= cutoff,
    )
    if keys:
        stmt = stmt.where(OutcomeFeedback.issue_key.in_(keys))
    stmt = stmt.group_by(OutcomeFeedback.outcome_kind, OutcomeFeedback.outcome_code)
    rows = db.execute(stmt).all()
    down = 0
    up = 0
    for kind, code, n in rows:
        sig = _signal_direction(str(kind), str(code))
        if sig == -1:
            down += int(n)
        elif sig == +1:
            up += int(n)
    directional = down + up
    if directional < settings.feedback_score_min_samples:
        return 0.0, []
    net = up - down
    raw = float(net) * float(settings.feedback_score_step)
    cap = float(settings.feedback_score_max_delta)
    adj = max(-cap, min(cap, raw))
    if adj == 0.0:
        return 0.0, []
    msg = (
        f"Operator outcome prior ({settings.feedback_score_lookback_days}d): "
        f"lower_priority_signals={down}, raise_priority_signals={up}, adjustment={adj:+.1f}"
    )
    factor: dict[str, Any] = {
        "kind": "operator_feedback",
        "message": msg,
        "refs": {
            "zone_id": zone_id,
            "down_signals": down,
            "up_signals": up,
            "adjustment": adj,
            "lookback_days": settings.feedback_score_lookback_days,
        },
    }
    return adj, [factor]


def submit_outcome_feedback(
    *,
    db: Session,
    body: OutcomeSubmitRequest,
    actor_override: str | None = None,
) -> OutcomeFeedback:
    issue_key = _resolve_issue_key(body)
    kind = body.outcome_kind.strip().lower()
    code = body.outcome_code.strip().lower()
    if kind not in ALLOWED_CODES_BY_KIND:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid outcome_kind; allowed: {sorted(ALLOWED_CODES_BY_KIND)}",
        )
    allowed = ALLOWED_CODES_BY_KIND[kind]
    if code not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid outcome_code for outcome_kind={body.outcome_kind}; allowed: {sorted(allowed)}",
        )

    if body.target_inspection_id is not None and db.get(Inspection, body.target_inspection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target_inspection_id not found")

    row_issue_state: IssueState | None = None
    if body.issue_state_id is not None:
        row_issue_state = db.get(IssueState, body.issue_state_id)
        if row_issue_state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue_state_id not found")
        if row_issue_state.org_scope != org_scope_for(body.org_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="issue_state_id org_scope does not match org_id on this request",
            )
        if row_issue_state.asset_zone_id != body.asset_zone_id.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="issue_state_id asset_zone_id does not match request",
            )
        if row_issue_state.issue_key != issue_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="issue_state_id issue_key does not match request",
            )

    if body.issue_state_event_id is not None:
        ev = db.get(IssueStateEvent, body.issue_state_event_id)
        if ev is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue_state_event_id not found")
        if row_issue_state is not None and ev.issue_state_id != row_issue_state.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="issue_state_event_id does not belong to issue_state_id",
            )
        if row_issue_state is None:
            parent = db.get(IssueState, ev.issue_state_id)
            if parent is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue_state for event not found")
            if parent.org_scope != org_scope_for(body.org_id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="issue_state_event parent org_scope does not match org_id on this request",
                )
            if parent.asset_zone_id != body.asset_zone_id.strip() or parent.issue_key != issue_key:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="issue_state_event parent does not match asset_zone_id/issue_key",
                )

    primary: Detection | None = None
    if body.primary_detection_id is not None:
        primary = db.get(Detection, body.primary_detection_id)
        if primary is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="primary_detection_id not found")
        if body.target_inspection_id is not None and primary.inspection_id != body.target_inspection_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="primary_detection_id must belong to target_inspection_id",
            )

    if body.detection_refs:
        for ref in body.detection_refs:
            rid = ref.get("detection_id")
            if rid is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="detection_refs entries require detection_id",
                )
            try:
                uid = uuid.UUID(str(rid))
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="detection_refs.detection_id must be a UUID",
                )
            if db.get(Detection, uid) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"detection_id not found: {uid}",
                )

    cap_label = body.captured_priority_label
    cap_score = body.captured_priority_score
    if (
        cap_label is None
        and cap_score is None
        and body.target_inspection_id is not None
    ):
        mr = db.scalar(
            select(MaintenanceRecommendation)
            .where(
                MaintenanceRecommendation.target_inspection_id == body.target_inspection_id,
                MaintenanceRecommendation.asset_zone_id == body.asset_zone_id.strip(),
            )
            .order_by(MaintenanceRecommendation.priority_rank.asc(), MaintenanceRecommendation.id.asc())
            .limit(1)
        )
        if mr is not None:
            cap_label = mr.priority_label
            cap_score = mr.priority_score

    model_name = primary.model_name if primary else None
    model_version = primary.model_version if primary else None

    fb_id = uuid.uuid4()
    row = OutcomeFeedback(
        id=fb_id,
        actor=actor_override if actor_override is not None else body.actor,
        org_scope=org_scope_for(body.org_id),
        org_id=body.org_id,
        asset_zone_id=body.asset_zone_id.strip(),
        issue_key=issue_key,
        outcome_kind=kind,
        outcome_code=code,
        notes=body.notes,
        context=body.context,
        target_inspection_id=body.target_inspection_id,
        issue_state_id=body.issue_state_id,
        issue_state_event_id=body.issue_state_event_id,
        primary_detection_id=body.primary_detection_id,
        detection_refs=body.detection_refs,
        captured_priority_label=cap_label,
        captured_priority_score=cap_score,
        model_name=model_name,
        model_version=model_version,
    )
    db.add(row)
    summary = f"Outcome {kind}/{code} for {issue_key} in {body.asset_zone_id.strip()}"
    refs: dict[str, object | None] = {
        "outcome_feedback_id": str(fb_id),
        "outcome_kind": kind,
        "outcome_code": code,
        "target_inspection_id": str(body.target_inspection_id) if body.target_inspection_id else None,
        "primary_detection_id": str(body.primary_detection_id) if body.primary_detection_id else None,
        "actor": body.actor,
    }
    append_zone_decision_log(
        db=db,
        org_id=body.org_id,
        asset_zone_id=body.asset_zone_id.strip(),
        event_type="operator_outcome",
        issue_key=issue_key,
        inspection_id=body.target_inspection_id,
        outcome_feedback_id=fb_id,
        payload={"summary": summary, "refs": refs},
    )
    db.commit()
    db.refresh(row)
    return row


def list_outcome_feedback(
    *,
    db: Session,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    org_id: uuid.UUID | None = None,
    asset_zone_id: str | None = None,
    issue_key: str | None = None,
    outcome_kind: str | None = None,
    target_inspection_id: uuid.UUID | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[OutcomeFeedback], int]:
    """Paginated export list; newest ``created_at`` first. Omitting ``org_id`` skips org_scope filter."""
    stmt = select(OutcomeFeedback)
    if created_from is not None:
        stmt = stmt.where(OutcomeFeedback.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(OutcomeFeedback.created_at <= created_to)
    if org_id is not None:
        stmt = stmt.where(OutcomeFeedback.org_scope == org_scope_for(org_id))
    else:
        stmt = stmt.where(OutcomeFeedback.org_scope == "global")
    if asset_zone_id is not None:
        stmt = stmt.where(OutcomeFeedback.asset_zone_id == asset_zone_id.strip())
    if issue_key is not None:
        stmt = stmt.where(OutcomeFeedback.issue_key == issue_key.strip())
    if outcome_kind is not None:
        stmt = stmt.where(OutcomeFeedback.outcome_kind == outcome_kind.strip().lower())
    if target_inspection_id is not None:
        stmt = stmt.where(OutcomeFeedback.target_inspection_id == target_inspection_id)
    if model_name is not None:
        stmt = stmt.where(OutcomeFeedback.model_name == model_name.strip())
    if model_version is not None:
        stmt = stmt.where(OutcomeFeedback.model_version == model_version.strip())

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(OutcomeFeedback.created_at.desc(), OutcomeFeedback.id.asc()).limit(limit).offset(offset)
    rows = list(db.scalars(stmt).all())
    return rows, int(total)
