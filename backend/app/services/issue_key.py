"""Stable ``issue_key`` strings for issue state identity (v1)."""


def build_issue_key(detection_type: str, class_name: str, *, subtype: str = "default") -> str:
    """Return ``{detection_type}:{class_name}:{subtype}`` in lowercase trimmed segments."""
    dt = detection_type.strip().lower()
    cls = class_name.strip().lower()
    sub = subtype.strip().lower() or "default"
    return f"{dt}:{cls}:{sub}"
