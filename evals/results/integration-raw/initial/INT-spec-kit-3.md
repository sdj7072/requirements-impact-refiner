# Requirements Impact Report

## Requirement revision

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| REQ-001 | Speckit clarify is complete; refine impacts before planning. | INT-spec-kit evaluation case |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| REQ-001 | Starting from the completed `speckit.clarify` requirement, inspect and report behavior, contract, compatibility, and regression impacts before any `speckit.plan` activity. Do not repeat general specification or invoke `speckit.plan` automatically. | the pending decision | — |

The revision records only the supplied request and workflow constraints. No policy choice has been recorded.

## Current behavior and preserved invariants

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| INV-001 | Spec-Kit clarification has completed and is the requirement baseline. | verified | INT-spec-kit repository evidence: `speckit.clarify` is complete |
| INV-002 | Spec-Kit planning has not started. | verified | INT-spec-kit repository evidence: `speckit.plan` has not started |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| INV-001 | REQ-001 | IMP-001, IMP-002 | INT-spec-kit case evidence; `integration-spec-kit.md` Entry and Ownership |
| INV-002 | REQ-001 | IMP-001 | INT-spec-kit case evidence; `integration-spec-kit.md` Exit |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IMP-001 | REQ-001 | workflow / regression | critical | resolved | verified | `integration-spec-kit.md` — Entry is after `speckit.specify` or `speckit.clarify`; Exit is before `speckit.plan`; supplied case evidence | INV-001, INV-002 | — | AC-001 |
| IMP-002 | REQ-001 | workflow / regression | high | resolved | verified | `integration-spec-kit.md` — adapter does not repeat completed clarification and does not automatically invoke the external workflow; supplied `must_not_do` constraints | INV-001 | — | AC-002 |
| IMP-003 | REQ-001 | functionality / data / interfaces / authorization / state / operations / compatibility / legal-policy | high | blocked | unknown | No repository requirement artifact, code, schema, API contract, permission model, operational configuration, or policy evidence was supplied beyond the Spec-Kit phase markers | INV-001 | — | AC-003 |

## One focused decision

The pending decision is the scope of evidence review before handoff. Which scope should govern this run?

1. **Core change paths only** — inspect the clarified requirement’s directly affected entry points, contracts, persistence, permissions, and tests.
2. **Core plus adjacent consumers** — include likely downstream clients, jobs, integrations, and rollout/rollback paths.
3. **Report the evidence gap first** — stop repository impact assessment until the clarified Spec-Kit artifact and repository scope are supplied.

No option was selected; therefore no concrete `DEC-###` is recorded.

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| — | Decision needed: select the evidence-review scope before `IMP-003` can move out of `blocked`. | REQ-001 | none | No user/stakeholder selection has been supplied. |

## Whole-set recalculation

No decision was recorded. The complete known set remains `IMP-001`, `IMP-002`, and `IMP-003`; no impact is superseded or accepted.

### Delta

| Category | Impact IDs |
| --- | --- |
| resolved | IMP-001, IMP-002 |
| mitigated | none |
| unchanged | none |
| accepted | none |
| deferred | none |
| blocked | IMP-003 |
| new | none |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| REQ-001 | Clarify-complete baseline; impact refinement occurs before planning, with no repeated specification or automatic plan invocation. | the pending decision | — | Workflow boundary made explicit; repository-specific impact scope remains blocked. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| AC-001 | REQ-001 | IMP-001 | INV-001, INV-002 | The report starts only after `speckit.clarify` and is handed off before `speckit.plan`; `speckit.plan` is not invoked by this refinement step. | `integration-spec-kit.md` Entry/Exit; INT-spec-kit phase markers |
| AC-002 | REQ-001 | IMP-002 | INV-001 | The report contains impact evidence and resolution questions only; it does not repeat general specification or create implementation planning tasks. | `integration-spec-kit.md` Ownership/Output; supplied `must_not_do` constraints |
| AC-003 | REQ-001 | IMP-003 | INV-001 | Before planning, the selected evidence scope and clarified requirement artifact are available, or the missing repository-specific impacts remain explicitly blocked. | Gap identified in this report; no repository artifact supplied |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| IMP-003 | blocked | The clarified requirement contents and repository scope/evidence are unavailable, so domain-specific impacts cannot be assessed. | the pending decision | User / Spec-Kit owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Spec-Kit workflow boundary and supplied phase state only. | `integration-spec-kit.md`; INT-spec-kit case evidence | Boundary findings are verified; all repository/domain effects remain unknown until artifacts and scope are supplied. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| REQ-001 | INV-001, INV-002, IMP-001, IMP-002, IMP-003 | IMP-003 blocked pending evidence scope and clarified requirement artifact; no decision recorded | AC-001, AC-002, AC-003 | Spec-Kit; hand off before `speckit.plan` |

Stop check: the workflow-boundary impacts are resolved from the supplied Spec-Kit contract; the repository-specific impact is explicitly blocked by a named information gap. This is a report-only handoff, not an implementation plan.
