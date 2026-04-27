from app.models.detection import Detection
from app.models.inspection import Inspection


def build_asset_zone_id(d: Detection, *, inspection: Inspection | None = None) -> str:
    """
    Deterministic asset/zone key (plan precedence, simplified):
    - ``asset_zone_hint`` when set on the detection
    - else ``asset_hint`` + class + coarse centroid bucket when inspection has ``asset_hint``
    - else ``site_hint`` (inspection, then detection attributes) + class + bucket
    """
    if d.asset_zone_hint:
        return d.asset_zone_hint
    site = "site-unknown"
    if inspection and inspection.site_hint:
        site = inspection.site_hint.strip() or site
    elif d.extra_attributes and isinstance(d.extra_attributes, dict):
        raw_site = d.extra_attributes.get("site_hint")
        if raw_site:
            site = str(raw_site).strip() or site
    cx = d.centroid_x if d.centroid_x is not None else (d.bbox_xmin + d.bbox_xmax) / 2.0
    cy = d.centroid_y if d.centroid_y is not None else (d.bbox_ymin + d.bbox_ymax) / 2.0
    bx = int(cx * 10)
    by = int(cy * 10)
    cls = d.class_name.lower()
    if inspection and inspection.asset_hint:
        asset = inspection.asset_hint.strip() or "asset-unknown"
        return f"{site}:{asset}:{cls}:{bx}:{by}"
    return f"{site}:{cls}:{bx}:{by}"
