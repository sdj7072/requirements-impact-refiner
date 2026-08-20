# Refinement Loop

Present outputs in this order:

```text
Requirement revision
Current behavior and preserved invariants
Impact ledger ordered by severity and evidence confidence
One focused decision with 2–3 options
Recorded decision
Whole-set recalculation
Delta: resolved / mitigated / unchanged / accepted / deferred / blocked / new
Stop check and planning handoff
```

Create or revise `REQ-###`, then establish current behavior and `INV-###` before proposing a change. Show the ledger first. Ask one question only if a decision is needed, provide two or three concrete options, and record the answer as `DEC-###`.

After every decision, re-evaluate every known `IMP-###`, not just the item discussed. Mark obsolete findings `superseded`, identify new impacts, and show the complete delta. If no decision is made, still show every delta category (`resolved`, `mitigated`, `unchanged`, `accepted`, `deferred`, `blocked`, `new`) and write `new: none` when applicable. Delta categories are mutually exclusive: list every known `IMP-###` once only, never under a second category; initial `detected` or `refining` impacts are `unchanged`. Keep accepted risks linked to their decision; only evidence can resolve an impact.

Stop only when every material impact is `resolved`, `accepted`, `deferred` with rationale, or `blocked` with a named information gap. Silence is never acceptance. At stop, provide the refined requirement, report links, remaining risks, and `AC-###` criteria to the selected planning workflow; do not create an imperative work breakdown or its implementation plan.
