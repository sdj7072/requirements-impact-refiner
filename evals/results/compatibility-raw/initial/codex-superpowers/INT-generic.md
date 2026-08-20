# Generic Integration Entry-Gate Result

## Mode

`generic`

## Orchestrator ownership

No named orchestration workflow is active. This adapter remains the sole
workflow owner for this entry attempt; no external workflow is invoked.

## Entry status

**Not met.** The generic adapter requires both of the following before impact
refinement can begin:

- substantive change request text;
- affected repository scope or an evidence target concrete enough for
  inspection.

The requirement is approved, but its substantive text and scope/evidence
target were not supplied. Approval alone is insufficient.

## Required next input

Provide only the missing requirement text and affected repository scope (or a
concrete evidence target). This is an entry-gate request, not broad product
ideation.

## Explicit non-actions

No `REQ-###`, `INV-###`, `IMP-###`, `DEC-###`, or `AC-###` artifacts are
emitted. No canonical impact report is created. No implementation plan or
framework-specific command is added.

## Exit / handoff

Once the entry gate is met, consume the clarified requirement and its current
`Planning Handoff` state, then perform generic impact refinement. When
refinement stops, return the canonical impact report to the user’s chosen
planning method; do not start that method automatically.
