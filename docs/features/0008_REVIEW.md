# Feature 0008 — Code review (configurable risk rules)

Reviewed against `docs/features/0008_PLAN.md` and `commands/code_review_05.md`.

## Plan coverage

| Plan item | Status |
|-----------|--------|
| Config: merge behavior, max rows per eval, score clamp | `risk_rules_default_org_behavior`, `risk_rules_max_rows_per_eval`, `risk_rules_score_max` in `config.py` |
| Bootstrap JSON / seed script path | Not implemented (plan optional dev-only) |
| `RiskRule` model + migration | `risk_rules` table; Alembic **`0007_add_risk_rules`** (revises `0006`) |
| Indexes | Composite `ix_risk_rules_org_enabled_priority`; plan’s partial index on `enabled=true` not used (acceptable v1) |
| `risk_rule_context` + `risk_rule_eval` | Implemented; `match_version: 1` AND semantics; effects stack as `(base + Σ add) × Π mul`, SLA `Π sla_days_multiplier` |
| Wire into `recommendation_rules.score_zone` + engine | `score_zone` returns `(score, factors, summary, sla_mul)`; engine applies `sla_days_for_label × sla_mul` |
| Rationale `kind: risk_rule` with ids | `apply_risk_rule_effects` appends factors with `risk_rule_id`, `name`, `effect` |
| Admin `/risk-rules` GET/POST/PATCH | `app/api/routes/risk_rules.py`, registered in `main.py` |
| Docs | `INGEST_API.md` match/effect schema and load order |
| Tests | `test_risk_rule_eval.py`, extended `test_recommendation_rules.py`, `test_recommendation_engine.py`, API test |

## Context vs matchers (informational)

`RiskRuleContext` includes inspection fields, per-zone detection aggregates, frame lat/lon envelope, and `extra_metadata` for `inspection_metadata_contains`. It does **not** embed progression metric values or change-event counts as first-class fields—`match` cannot yet predicate on “crack_growth_rate &gt; X” without extending the schema. Acceptable for v1; progression still affects **base score** before rules run.

## Load order semantics (informational)

With `merge_global_then_org`, **all** org-scoped enabled rules (sorted by `priority`, `id`) are prepended before **all** global rules—so a global rule at priority `1` still runs after an org rule at priority `999`. Documented in `INGEST_API.md`; operators should set org priorities lower (earlier) than globals when they need strict ordering across scopes.

## Fixes and tests added in this review

1. **`INGEST_API.md`** — Zone-key bullet now states that **progression metrics** are included in the union (matching `recommendation_engine` behavior since feature 0007 follow-up).
2. **`test_load_merge_lists_org_rules_before_global`** — Locks merge ordering (org before global).
3. **`test_recommendation_engine_persists_sla_days_multiplier`** — Locks persisted `sla_days_suggested` when a catch-all rule applies `sla_days_multiplier: 0.5`.

## Data / API alignment

- HTTP JSON remains **snake_case** (`risk_rules`, `match`, `effect`, `sla_days_multiplier`).
- `match` / `effect` are plain objects at the Pydantic boundary (`dict[str, Any]`), not wrapped in `{ "data": ... }`.

## Style

- Evaluators stay pure against `RiskRuleContext`; DB reads isolated to `load_risk_rules` and engine orchestration—consistent with the plan.

## Tests

Full backend suite run after the above; all tests passed.
