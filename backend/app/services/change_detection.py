import uuid

from app.models.change_event import ChangeEvent
from app.models.detection import Detection
from app.services.alignment_matching import MatchedPair


def build_change_events(
    *,
    inspection_id,
    asset_zone_id: str,
    pairs: list[MatchedPair],
) -> list[ChangeEvent]:
    """Generate change events from non-persisted alignment outcomes."""
    events: list[ChangeEvent] = []
    for p in pairs:
        if p.change_type == "persisted":
            continue
        det: Detection | None = p.target or p.baseline
        class_name = det.class_name if det is not None else "unknown"
        events.append(
            ChangeEvent(
                id=uuid.uuid4(),
                asset_zone_id=asset_zone_id,
                inspection_id=inspection_id,
                event_type=p.change_type,
                event_payload={"class_name": class_name, "alignment_score": p.score},
            )
        )
    return events
