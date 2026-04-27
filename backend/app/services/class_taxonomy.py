from app.models.detection import DetectionType

ASSET_CLASSES = {
    "tower",
    "insulator",
    "pole",
    "transformer",
    "conductor",
}

DEFECT_CLASSES = {
    "crack",
    "corrosion",
    "broken_insulator",
    "hotspot",
}

ENVIRONMENTAL_HAZARD_CLASSES = {
    "vegetation_encroachment",
    "flooding",
    "smoke",
    "landslide",
}

CRACK_CLASSES = frozenset({"crack"})

VEGETATION_ENCROACHMENT_CLASSES = frozenset({"vegetation_encroachment"})


def map_class_to_detection_type(class_name: str) -> DetectionType | None:
    name = class_name.strip().lower()
    if name in ASSET_CLASSES:
        return DetectionType.asset
    if name in DEFECT_CLASSES:
        return DetectionType.defect
    if name in ENVIRONMENTAL_HAZARD_CLASSES:
        return DetectionType.environmental_hazard
    return None
