Validate the implemented feature for a specific feature id.

Inputs:
- The implemented code changes
- The related `docs/features/<id>_PLAN.md`
- Optional `docs/features/<id>_REVIEW.md` if a review already exists

Validation workflow:
1. Run project checks that exist in this repo (for example: lint, typecheck, tests, build).
2. Report only actionable results:
   - failing command
   - root cause
   - minimal fix recommendation
3. Confirm implemented behavior still aligns with the plan at a high level.
4. Keep output concise; avoid re-documenting the full feature.

Artifact rules:
- Default: do not create a new file.
- If explicitly requested, write a short report to `docs/features/<id>_VALIDATION.md`.

Output:
- Pass/fail summary for each check run.
- A short "ready for review/PR" recommendation with blockers (if any).
