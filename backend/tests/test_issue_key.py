from app.services.issue_key import build_issue_key


def test_build_issue_key_normalizes():
    assert build_issue_key("  DEFECT ", "Crack", subtype="  Default  ") == "defect:crack:default"


def test_build_issue_key_subtype():
    assert build_issue_key("environmental_hazard", "vegetation_encroachment", subtype="v2") == (
        "environmental_hazard:vegetation_encroachment:v2"
    )
