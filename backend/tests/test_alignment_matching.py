from uuid import uuid4

from app.models.detection import Detection, DetectionType
from app.services.alignment_matching import (
    bbox_iou,
    centroid_norm_distance,
    match_detection_sets,
)


def _det(*, cls: str, xmin: float, ymin: float, xmax: float, ymax: float, conf: float):
    return Detection(
        id=uuid4(),
        inspection_id=uuid4(),
        frame_id=uuid4(),
        detection_type=DetectionType.defect,
        class_name=cls,
        confidence=conf,
        bbox_xmin=xmin,
        bbox_ymin=ymin,
        bbox_xmax=xmax,
        bbox_ymax=ymax,
        model_name="yolo",
        model_version="v1",
    )


def test_bbox_iou_overlap():
    a = _det(cls="crack", xmin=0.1, ymin=0.1, xmax=0.5, ymax=0.5, conf=0.9)
    b = _det(cls="crack", xmin=0.3, ymin=0.3, xmax=0.7, ymax=0.7, conf=0.9)
    assert 0 < bbox_iou(a, b) < 1


def test_match_detection_sets_persisted_and_appeared():
    baseline = [_det(cls="crack", xmin=0.1, ymin=0.1, xmax=0.5, ymax=0.5, conf=0.9)]
    target = [
        _det(cls="crack", xmin=0.12, ymin=0.1, xmax=0.52, ymax=0.5, conf=0.9),
        _det(cls="crack", xmin=0.7, ymin=0.7, xmax=0.9, ymax=0.9, conf=0.9),
    ]
    pairs = match_detection_sets(
        baseline, target, iou_threshold=0.3, min_confidence=0.2
    )
    kinds = sorted(p.change_type for p in pairs)
    assert kinds == ["appeared", "persisted"]


def test_centroid_norm_distance():
    a = _det(cls="crack", xmin=0.0, ymin=0.0, xmax=0.2, ymax=0.2, conf=0.9)
    b = _det(cls="crack", xmin=0.8, ymin=0.8, xmax=1.0, ymax=1.0, conf=0.9)
    assert centroid_norm_distance(a, b) > 0.5


def test_match_detection_sets_disappeared_when_class_mismatch():
    baseline = [_det(cls="crack", xmin=0.1, ymin=0.1, xmax=0.5, ymax=0.5, conf=0.9)]
    target = [_det(cls="corrosion", xmin=0.1, ymin=0.1, xmax=0.5, ymax=0.5, conf=0.9)]
    pairs = match_detection_sets(
        baseline, target, iou_threshold=0.3, min_confidence=0.2
    )
    kinds = sorted(p.change_type for p in pairs)
    assert kinds == ["appeared", "disappeared"]


def test_match_detection_sets_rejects_distant_centroids():
    baseline = [_det(cls="crack", xmin=0.0, ymin=0.0, xmax=0.2, ymax=0.2, conf=0.9)]
    target = [_det(cls="crack", xmin=0.8, ymin=0.8, xmax=1.0, ymax=1.0, conf=0.9)]
    pairs = match_detection_sets(
        baseline,
        target,
        iou_threshold=0.01,
        min_confidence=0.2,
        max_centroid_norm_distance=0.1,
    )
    kinds = sorted(p.change_type for p in pairs)
    assert kinds == ["appeared", "disappeared"]
