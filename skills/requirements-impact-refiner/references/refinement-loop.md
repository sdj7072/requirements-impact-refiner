# Refinement Loop

Choose one branch and present only its sections:

```text
pre-decision: Report State → requirement → current behavior/invariants → ledger
              → Decision Needed (one question, 2–3 options) → Impact Delta → handoff
post-decision: Report State → requirement → current behavior/invariants → ledger
               → Decisions and Accepted Risks → Impact Delta → handoff
```

Create or revise `REQ-###`, then establish current behavior and `INV-###` before proposing a change. Show the ledger first. Ask one question only if a decision is needed, provide two or three concrete options, and record the answer as `DEC-###`.

Before selection, use the pre-decision template. It forbids concrete decision IDs and the recorded-decisions section; option-specific mechanics stay in **Decision Needed**. After selection, switch to the post-decision template, record the choice, and re-evaluate every known `IMP-###`.

Both phases show all delta categories: `resolved`, `mitigated`, `unchanged`, `accepted`, `deferred`, `blocked`, `superseded`, and `new`. Write `none` for empty categories. Categories are mutually exclusive and cover every known impact exactly once. Initial `detected`/`refining` impacts are `unchanged`; a newly discovered impact appears only under `new` that turn; other states use their matching category. Only evidence resolves an impact, and acceptance requires its decision.

Stop only when every material impact is `resolved`, `accepted`, `deferred` with rationale, or `blocked` with a named information gap. Silence is never acceptance. At stop, provide the refined requirement, report links, remaining risks, and `AC-###` criteria to the selected planning workflow; do not create an imperative work breakdown or its implementation plan.
