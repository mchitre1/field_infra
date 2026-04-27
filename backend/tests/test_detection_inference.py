from app.core.config import Settings
from app.services.class_taxonomy import map_class_to_detection_type
from app.services.detection_inference import run_frame_detection


def _mk_png_bytes(color: tuple[int, int, int]) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=color).save(buf, format="PNG")
    return buf.getvalue()


def test_taxonomy_mapping_known_classes():
    assert map_class_to_detection_type("tower") is not None
    assert map_class_to_detection_type("crack") is not None
    assert map_class_to_detection_type("vegetation_encroachment") is not None
    assert map_class_to_detection_type("unknown-thing") is None


def test_inference_threshold_filters():
    settings = Settings(
        database_url="sqlite://",
        s3_bucket="b",
        aws_region="us-east-1",
        inference_confidence_threshold=0.95,
    )
    dets = run_frame_detection(settings=settings, frame_bytes=_mk_png_bytes((255, 255, 255)))
    assert dets == []


def test_inference_returns_normalized_bbox():
    settings = Settings(database_url="sqlite://", s3_bucket="b", aws_region="us-east-1")
    dets = run_frame_detection(settings=settings, frame_bytes=_mk_png_bytes((180, 180, 180)))
    assert len(dets) == 1
    d = dets[0]
    assert 0.0 <= d.bbox_xmin < d.bbox_xmax <= 1.0
    assert 0.0 <= d.bbox_ymin < d.bbox_ymax <= 1.0
    assert 0.0 <= d.confidence <= 1.0
