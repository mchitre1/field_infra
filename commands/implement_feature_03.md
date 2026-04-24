Implement one feature from one plan file.

Inputs:
- The relevant `docs/features/<id>_PLAN.md` (single feature plan)
- Existing codebase
- Optional `docs/PRODUCT_BRIEF.md` for additional product context

Execution rules:
1. Treat the plan as the implementation scope and do not restate or rewrite it.
2. Assume one plan file corresponds to one feature. Implement that feature only.
3. Keep edits small, targeted, and consistent with existing code patterns.
4. Update tests only where behavior changed or new behavior was added.
5. Use the plan's feature description and technical details as the primary implementation context.
6. If you find a major gap or ambiguity in the plan, ask one concise clarification question; otherwise proceed.
7. Do not create new planning/review artifacts in this step.

Output:
- Implemented code changes in the repository, ready for validation and review.
- A concise response listing:
  - files changed
  - any assumptions made
  - any follow-up items that should be reviewed
