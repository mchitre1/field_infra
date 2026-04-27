"""Load persisted risk rules and apply composed effects to base recommendation scores."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.risk_rule import RiskRule
from app.services.risk_rule_context import RiskRuleContext


def _intervals_overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    if a0 > a1:
        a0, a1 = a1, a0
    if b0 > b1:
        b0, b1 = b1, b0
    return not (a1 < b0 or b1 < a0)


def rule_matches(*, match: dict[str, Any], ctx: RiskRuleContext) -> bool:
    """AND semantics over recognized ``match_version: 1`` keys; unknown ``match_version`` → no match."""
    mv = match.get("match_version", 1)
    if mv != 1:
        return False

    if match.get("source_types"):
        allowed = {str(s).strip().lower() for s in match["source_types"]}
        if ctx.source_type.lower() not in allowed:
            return False

    if match.get("asset_classes_any"):
        need = {str(s).strip().lower() for s in match["asset_classes_any"]}
        if not (ctx.asset_class_names & need):
            return False

    pat = match.get("asset_hint_pattern")
    if pat:
        try:
            if not re.search(str(pat), ctx.asset_hint or "", flags=re.IGNORECASE):
                return False
        except re.error:
            return False

    if "min_confidence" in match and match["min_confidence"] is not None:
        if ctx.max_risk_confidence < float(match["min_confidence"]):
            return False
    if "max_confidence" in match and match["max_confidence"] is not None:
        if ctx.max_risk_confidence > float(match["max_confidence"]):
            return False

    if match.get("severity_in"):
        allowed = {str(s).strip().lower() for s in match["severity_in"]}
        if not (ctx.severities_present & allowed):
            return False

    lat_keys = ("lat_min", "lat_max", "lon_min", "lon_max")
    if any(k in match for k in lat_keys):
        if not all(k in match and match[k] is not None for k in lat_keys):
            return False
        if ctx.latitude is None or ctx.longitude is None:
            return False
        lat, lon = ctx.latitude, ctx.longitude
        if not (
            float(match["lat_min"]) <= lat <= float(match["lat_max"])
            and float(match["lon_min"]) <= lon <= float(match["lon_max"])
        ):
            return False

    box = match.get("frame_lat_lon_box")
    if isinstance(box, dict) and box:
        fk = ("lat_min", "lat_max", "lon_min", "lon_max")
        if not all(box.get(k) is not None for k in fk):
            return False
        if (
            ctx.frame_lat_min is None
            or ctx.frame_lat_max is None
            or ctx.frame_lon_min is None
            or ctx.frame_lon_max is None
        ):
            return False
        b_lat0, b_lat1 = float(box["lat_min"]), float(box["lat_max"])
        b_lon0, b_lon1 = float(box["lon_min"]), float(box["lon_max"])
        if not _intervals_overlap(ctx.frame_lat_min, ctx.frame_lat_max, b_lat0, b_lat1):
            return False
        if not _intervals_overlap(ctx.frame_lon_min, ctx.frame_lon_max, b_lon0, b_lon1):
            return False

    meta_req = match.get("inspection_metadata_contains")
    if isinstance(meta_req, dict) and meta_req:
        for k, v in meta_req.items():
            if ctx.extra_metadata.get(k) != v:
                return False

    return True


def load_risk_rules(*, db: Session, settings: Settings, org_id: uuid.UUID | None) -> list[RiskRule]:
    """Load enabled rules for evaluation, ordered per ``risk_rules_default_org_behavior``."""
    stmt = select(RiskRule).where(RiskRule.enabled.is_(True))
    behavior = settings.risk_rules_default_org_behavior.strip().lower()
    if behavior == "global_only":
        stmt = stmt.where(RiskRule.org_id.is_(None))
    else:
        stmt = stmt.where(or_(RiskRule.org_id.is_(None), RiskRule.org_id == org_id))
    rows = list(
        db.scalars(stmt.order_by(RiskRule.priority.asc(), RiskRule.id.asc())).all()
    )
    if behavior == "merge_global_then_org" and org_id is not None:
        org_rows = [r for r in rows if r.org_id == org_id]
        glo_rows = [r for r in rows if r.org_id is None]
        rows = sorted(org_rows, key=lambda r: (r.priority, str(r.id))) + sorted(
            glo_rows, key=lambda r: (r.priority, str(r.id))
        )
    lim = settings.risk_rules_max_rows_per_eval
    return rows[:lim]


def apply_risk_rule_effects(
    *,
    settings: Settings,
    rules: list[RiskRule],
    ctx: RiskRuleContext,
    base_score: float,
) -> tuple[float, list[dict[str, Any]], float]:
    """Return ``(final_score, rationale_factors, sla_days_multiplier)``.

    Composition: sum all matching ``score_add``; multiply all matching ``score_multiplier``
    (defaults 0 and 1 respectively); multiply SLA days by each matching ``sla_days_multiplier``.
    Final score clamped to ``[0, risk_rules_score_max]``.
    """
    add = 0.0
    mul = 1.0
    sla_mul = 1.0
    fired: list[dict[str, Any]] = []

    for rule in rules:
        if not rule_matches(match=rule.match, ctx=ctx):
            continue
        eff = rule.effect if isinstance(rule.effect, dict) else {}
        add += float(eff.get("score_add", 0.0) or 0.0)
        sm = eff.get("score_multiplier", 1.0)
        if sm is not None:
            mul *= float(sm)
        sdm = eff.get("sla_days_multiplier", 1.0)
        if sdm is not None:
            sla_mul *= float(sdm)
        fired.append(
            {
                "kind": "risk_rule",
                "message": f"Risk rule “{rule.name}” applied",
                "refs": {
                    "risk_rule_id": str(rule.id),
                    "name": rule.name,
                    "effect": eff,
                    "zone_id": ctx.zone_id,
                },
            }
        )

    raw = (base_score + add) * mul
    cap = float(settings.risk_rules_score_max)
    final = min(cap, max(0.0, raw))
    return final, fired, sla_mul
