import math
from dataclasses import dataclass

from app.models.detection import Detection


@dataclass
class MatchedPair:
    """One alignment result row between baseline and target detections."""

    baseline: Detection | None
    target: Detection | None
    score: float
    change_type: str


def bbox_iou(a: Detection, b: Detection) -> float:
    x1 = max(a.bbox_xmin, b.bbox_xmin)
    y1 = max(a.bbox_ymin, b.bbox_ymin)
    x2 = min(a.bbox_xmax, b.bbox_xmax)
    y2 = min(a.bbox_ymax, b.bbox_ymax)
    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a.bbox_xmax - a.bbox_xmin) * max(0.0, a.bbox_ymax - a.bbox_ymin)
    area_b = max(0.0, b.bbox_xmax - b.bbox_xmin) * max(0.0, b.bbox_ymax - b.bbox_ymin)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def _centroid(d: Detection) -> tuple[float, float]:
    cx = d.centroid_x if d.centroid_x is not None else (d.bbox_xmin + d.bbox_xmax) / 2.0
    cy = d.centroid_y if d.centroid_y is not None else (d.bbox_ymin + d.bbox_ymax) / 2.0
    return cx, cy


def centroid_norm_distance(a: Detection, b: Detection) -> float:
    ax, ay = _centroid(a)
    bx, by = _centroid(b)
    return math.hypot(ax - bx, ay - by)


def match_detection_sets(
    baseline: list[Detection],
    target: list[Detection],
    *,
    iou_threshold: float,
    min_confidence: float,
    max_centroid_norm_distance: float | None = None,
) -> list[MatchedPair]:
    """Greedy one-to-one matcher using IoU/type/class gates plus confidence floor."""
    base = [d for d in baseline if d.confidence >= min_confidence]
    tgt = [d for d in target if d.confidence >= min_confidence]
    used_targets: set[str] = set()
    out: list[MatchedPair] = []
    for b in base:
        best = None
        best_score = 0.0
        for t in tgt:
            if str(t.id) in used_targets:
                continue
            if b.detection_type != t.detection_type:
                continue
            if b.class_name.lower() != t.class_name.lower():
                continue
            if max_centroid_norm_distance is not None:
                if centroid_norm_distance(b, t) > max_centroid_norm_distance:
                    continue
            score = bbox_iou(b, t)
            if score >= iou_threshold and score > best_score:
                best = t
                best_score = score
        if best is None:
            out.append(MatchedPair(baseline=b, target=None, score=0.0, change_type="disappeared"))
        else:
            used_targets.add(str(best.id))
            out.append(MatchedPair(baseline=b, target=best, score=best_score, change_type="persisted"))
    for t in tgt:
        if str(t.id) not in used_targets:
            out.append(MatchedPair(baseline=None, target=t, score=0.0, change_type="appeared"))
    return out
