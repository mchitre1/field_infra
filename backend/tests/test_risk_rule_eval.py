import uuid
from dataclasses import replace

import pytest

from app.core.config import Settings, get_settings
from app.models.risk_rule import RiskRule
from app.services.risk_rule_context import RiskRuleContext
from app.services.risk_rule_eval import apply_risk_rule_effects, load_risk_rules, rule_matches

_BASE_CTX = RiskRuleContext(
    match_version=1,
    zone_id="z",
    source_type="drone",
    asset_hint="tower-1",
    site_hint="s",
    latitude=40.0,
    longitude=-74.0,
    extra_metadata={},
    asset_class_names=frozenset({"tower"}),
    max_risk_confidence=0.85,
    severities_present=frozenset({"high"}),
    frame_lat_min=40.0,
    frame_lat_max=40.1,
    frame_lon_min=-74.1,
    frame_lon_max=-74.0,
)


def _ctx(**kwargs) -> RiskRuleContext:
    return replace(_BASE_CTX, **kwargs)


def test_rule_matches_source_and_asset_class():
    m = {"match_version": 1, "source_types": ["drone"], "asset_classes_any": ["tower"]}
    assert rule_matches(match=m, ctx=_ctx()) is True
    assert rule_matches(match={**m, "source_types": ["mobile"]}, ctx=_ctx()) is False


def test_rule_matches_severity_in():
    m = {"match_version": 1, "severity_in": ["high", "critical"]}
    assert rule_matches(match=m, ctx=_ctx()) is True
    assert rule_matches(match={**m, "severity_in": ["low"]}, ctx=_ctx()) is False


def test_rule_matches_inspection_bbox():
    m = {"match_version": 1, "lat_min": 39.0, "lat_max": 41.0, "lon_min": -75.0, "lon_max": -73.0}
    assert rule_matches(match=m, ctx=_ctx()) is True
    assert rule_matches(match={**m, "lat_max": 39.5}, ctx=_ctx()) is False


def test_rule_matches_frame_lat_lon_box_overlap():
    m = {
        "match_version": 1,
        "frame_lat_lon_box": {"lat_min": 40.05, "lat_max": 41.0, "lon_min": -75.0, "lon_max": -73.0},
    }
    assert rule_matches(match=m, ctx=_ctx()) is True


def test_rule_rejects_unknown_match_version():
    assert rule_matches(match={"match_version": 99}, ctx=_ctx()) is False


def test_apply_effects_stack_multipliers_and_add():
    ctx = _ctx(max_risk_confidence=0.9)
    rules = [
        RiskRule(
            id=uuid.uuid4(),
            org_id=None,
            priority=1,
            enabled=True,
            name="r1",
            match={"match_version": 1, "min_confidence": 0.5},
            effect={"score_add": 10.0, "score_multiplier": 2.0},
        ),
        RiskRule(
            id=uuid.uuid4(),
            org_id=None,
            priority=2,
            enabled=True,
            name="r2",
            match={"match_version": 1, "min_confidence": 0.5},
            effect={"score_add": 5.0, "score_multiplier": 1.5, "sla_days_multiplier": 0.8},
        ),
    ]
    final, fired, sla = apply_risk_rule_effects(settings=Settings(), rules=rules, ctx=ctx, base_score=20.0)
    assert final == pytest.approx((20.0 + 10.0 + 5.0) * 2.0 * 1.5)
    assert len(fired) == 2
    assert sla == pytest.approx(0.8)


def test_load_rules_global_only_filters_org_rows(sqlite_session, monkeypatch):
    oid = uuid.uuid4()
    sqlite_session.add_all(
        [
            RiskRule(
                id=uuid.uuid4(),
                org_id=None,
                priority=1,
                enabled=True,
                name="g",
                match={"match_version": 1},
                effect={"score_add": 1.0},
            ),
            RiskRule(
                id=uuid.uuid4(),
                org_id=oid,
                priority=1,
                enabled=True,
                name="o",
                match={"match_version": 1},
                effect={"score_add": 99.0},
            ),
        ]
    )
    sqlite_session.commit()
    monkeypatch.setenv("RISK_RULES_DEFAULT_ORG_BEHAVIOR", "global_only")
    get_settings.cache_clear()
    try:
        rows = load_risk_rules(db=sqlite_session, settings=get_settings(), org_id=oid)
        assert len(rows) == 1
        assert rows[0].name == "g"
    finally:
        monkeypatch.delenv("RISK_RULES_DEFAULT_ORG_BEHAVIOR", raising=False)
        get_settings.cache_clear()


def test_load_merge_lists_org_rules_before_global(sqlite_session):
    """merge_global_then_org: all org-scoped rows precede global rows (each group sorted by priority, id)."""
    oid = uuid.uuid4()
    sqlite_session.add_all(
        [
            RiskRule(
                id=uuid.uuid4(),
                org_id=None,
                priority=1,
                enabled=True,
                name="global_low_priority",
                match={"match_version": 1},
                effect={},
            ),
            RiskRule(
                id=uuid.uuid4(),
                org_id=oid,
                priority=99,
                enabled=True,
                name="org_high_priority",
                match={"match_version": 1},
                effect={},
            ),
        ]
    )
    sqlite_session.commit()
    rows = load_risk_rules(
        db=sqlite_session,
        settings=Settings(risk_rules_default_org_behavior="merge_global_then_org"),
        org_id=oid,
    )
    names = [r.name for r in rows]
    assert names == ["org_high_priority", "global_low_priority"]
