# Refinement Loop

Choose one branch and present only its sections:

```text
pre-decision: Report State → requirement → current behavior/invariants → ledger
              → Decision Needed (one question, 2–3 options) → Impact Delta → handoff
post-decision: Report State → requirement → current behavior/invariants → ledger
               → Decisions and Accepted Risks → Impact Delta → handoff
```

Before revising, first inspect `.requirements-impact-refiner/reports/RPT-###/current.json` when the report ID is known. Accept its fast path only when the pointer schema is valid, its selected JSON and Markdown are repository-relative regular files, and the selected Markdown bytes match `markdown_sha256`. Preserve the state, IDs, and unchanged facts; inspect only evidence affected by the new request. The publisher validates the exact transition and calculates whether the authored Delta agrees.

If no valid pointer exists, locate the latest v0.3+ Markdown predecessor. If none exists, create a stable report ID at Revision 1 with predecessor `none`. Otherwise preserve the report and known impact IDs, increment the revision by exactly one, and hash the predecessor's exact bytes. If the predecessor cannot be obtained, disclose the lineage gap instead of guessing. Then create or revise `REQ-###`, establish current behavior and `INV-###`, and ask one question only when a decision is needed.

Before selection, use the pre-decision template. It forbids concrete decision IDs and the recorded-decisions section; option-specific mechanics stay in **Decision Needed**. After selection, switch to the post-decision template, record the choice, and re-evaluate every known `IMP-###`.

Both phases show all delta categories: `resolved`, `mitigated`, `unchanged`, `accepted`, `deferred`, `blocked`, `superseded`, `reopened`, and `new`. Write `none` for empty categories. Categories are mutually exclusive and cover every current or predecessor impact exactly once. On the first report, every impact is `new`. Later, compute each category from the predecessor transition: stable states are `unchanged`; newly discovered IDs are `new`; terminal-to-active transitions are `reopened`; removed IDs are invalid unless retained as `superseded`. Only evidence resolves an impact, and acceptance requires its decision.

Run deterministic validation with `--previous` for revisions. When it is unavailable, perform the same comparison conceptually and disclose that deterministic validation did not run.

Stop only when every material impact is `resolved`, `accepted`, `deferred` with rationale, or `blocked` with a named information gap. Silence is never acceptance. At stop, provide the refined requirement, report links, remaining risks, and `AC-###` criteria to the selected planning workflow; do not create an imperative work breakdown or its implementation plan.
