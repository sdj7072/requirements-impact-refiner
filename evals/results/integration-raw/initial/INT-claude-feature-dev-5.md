# Requirements Impact Report — Claude feature-dev integration

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Feature-dev clarification is complete; analyze change impact before architecture design. | Supplied evidence: “Feature-dev Phase 3 complete; Phase 4 architecture not started.” |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Use the completed Phase 3 clarification as the baseline, preserve current behavior and explicit compatibility obligations, and return a canonical report-only impact handoff before Phase 4 architecture. Do not select architecture mechanics or create implementation tasks. | The pending decision; no recorded decision | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Feature-dev Phase 3 clarification is complete and is the requirements baseline. | `verified` | Supplied task evidence: “Feature-dev Phase 3 complete.” |
| `INV-002` | Feature-dev Phase 4 architecture has not started; no architecture mechanic is selected. | `verified` | Supplied task evidence: “Phase 4 architecture not started.” |
| `INV-003` | This activity produces a canonical impact report and stops at the planning handoff; it does not repeat clarification, invoke architecture, or create an implementation work breakdown. | `verified` | `integration-claude-feature-dev.md` — Output/Exit; `refinement-loop.md` — stop check. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003` | Phase 3 completion is supplied, but the clarified artifact is unavailable. |
| `INV-002` | `REQ-001` | `IMP-008` | Phase 4-not-started status is supplied. |
| `INV-003` | `REQ-001` | `IMP-008` | Claude adapter boundary and refinement-loop stop rule. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Functionality / Regression | high | `blocked` | `unknown` | No clarified requirement, source, entry point, caller, feature flag, or test evidence was supplied. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | Data | high | `blocked` | `unknown` | No model, schema, serializer, migration, retention, cleanup, or fixture evidence was supplied. | — | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | Interfaces / Compatibility | high | `blocked` | `unknown` | No API/event contract, DTO, webhook, consumer, or compatibility-test evidence was supplied. | `INV-001` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | Authorization / Privacy | high | `blocked` | `unknown` | No authentication, role-check, data-classification, consent, deletion, or audit evidence was supplied. | `INV-001` | the pending decision | `AC-004` |
| `IMP-005` | `REQ-001` | State / Concurrency | high | `blocked` | `unknown` | No transaction boundary, state machine, queue, retry, ordering, timeout, idempotency, or race-test evidence was supplied. | — | the pending decision | `AC-005` |
| `IMP-008` | `REQ-001` | Workflow / Regression | critical | `blocked` | `inferred` | Phase 4 has not started; beginning architecture or implementation planning could encode unselected mechanics or revise the Phase 3 baseline. | `INV-002`, `INV-003` | the pending decision | `AC-008` |
| `IMP-006` | `REQ-001` | Operations | medium | `blocked` | `unknown` | No deployment, rollout, metric, alert, runbook, rollback, backup, or recovery evidence was supplied. | — | the pending decision | `AC-006` |
| `IMP-007` | `REQ-001` | Legal / Policy | medium | `blocked` | `unknown` | No retention schedule, regional rule, data inventory, license, or approval record was supplied. | — | the pending decision | `AC-007` |

## Decisions and Accepted Risks

No concrete recorded decision exists. The pending decision is the evidence boundary for the next pass: core-path inspection, repository-wide inspection, or supplied-artifacts-only handoff. No impact is accepted; blocked impacts remain blocked by named gaps.

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Preserve the completed Phase 3 clarification and hand off an evidence-backed impact report before Phase 4. | the pending decision; none recorded | none | `IMP-001`–`IMP-008` remain blocked; `new: none`. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Identify affected entry points, adjacent behavior, and regression coverage or gaps before Phase 4 relies on this report. | Requires the Phase 3 artifact, source, and tests; unavailable. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-001` | Identify data, schema, serialization, retention, migration, and integrity effects with validation criteria. | Requires models, schemas, migrations, and fixtures; unavailable. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-001` | Identify affected interfaces and supported-consumer compatibility behavior. | Requires contracts, consumers, and compatibility tests; unavailable. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-001` | Preserve or explicitly flag access, privacy, consent, deletion, and audit behavior. | Requires authorization and policy evidence; unavailable. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-001` | Preserve or explicitly revise transaction, retry, ordering, timeout, and idempotency behavior through a later recorded choice. | Requires runtime and concurrency evidence; unavailable. |
| `AC-006` | `REQ-001` | `IMP-006` | `INV-001` | Identify rollout, observability, rollback, and recovery requirements before implementation planning. | Requires deployment and operations evidence; unavailable. |
| `AC-007` | `REQ-001` | `IMP-007` | `INV-001` | Identify applicable legal, retention, regional, and policy constraints or record external validation gaps. | Requires policy and data-inventory evidence; unavailable. |
| `AC-008` | `REQ-001` | `IMP-008` | `INV-002`, `INV-003` | Treat no architecture mechanic or implementation task as selected before Phase 4 and an explicit decision. | Verified by Phase 4-not-started evidence and adapter boundary. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | `blocked` | Phase 3 clarification, repository scope, entry points, and tests are missing. | the pending decision | Requirement owner |
| `IMP-002` | `blocked` | Model, schema, migration, and retention evidence is missing. | the pending decision | Requirement owner |
| `IMP-003` | `blocked` | Contract, consumer, and compatibility evidence is missing. | the pending decision | Requirement owner |
| `IMP-004` | `blocked` | Authorization and privacy evidence is missing. | the pending decision | Requirement owner |
| `IMP-005` | `blocked` | Runtime and concurrency evidence is missing. | the pending decision | Requirement owner |
| `IMP-006` | `blocked` | Deployment and operations evidence is missing. | the pending decision | Requirement owner |
| `IMP-007` | `blocked` | Legal and policy evidence is missing. | the pending decision | Requirement owner |
| `IMP-008` | `blocked` | Phase 4 has not started and no explicit mechanics choice exists. | the pending decision | Feature-dev owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Claude feature-dev workflow boundary | `integration-claude-feature-dev.md`; supplied Phase 3/Phase 4 status | Entry and exit are verified; product behavior is not established. |
| Product repository and clarification | No source, diff, contract, schema, policy, deployment, test, or Phase 3 artifact supplied | Product-specific impacts remain unknown and blocked. |

## Whole-set Recalculation

No clarified artifact, repository evidence, or user selection was supplied after the baseline. The complete known set remains `IMP-001`–`IMP-008`; none is superseded or newly introduced. Each impact remains blocked.

## Delta

- **resolved:** none
- **mitigated:** none
- **unchanged:** none
- **accepted:** none
- **deferred:** none
- **blocked:** `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007`, `IMP-008`
- **new:** none

Categories are mutually exclusive; every known impact appears exactly once.

## One Focused Decision

Which evidence boundary should govern the next pass?

1. **Core-path inspection (recommended):** inspect the clarified change’s entry points, direct callers/callees, contracts, persistence, authorization, operations, and adjacent tests.
2. **Repository-wide inspection:** inspect all potentially affected modules and cross-cutting policies before Phase 4.
3. **Supplied-artifacts-only handoff:** keep product impacts blocked and carry the named gaps into Phase 4.

No option is selected in the supplied context. This is an evidence-boundary question, not a selection of implementation mechanics; no concrete decision ID is recorded.

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `INV-001`–`INV-003`, `IMP-001`–`IMP-008` | Functionality, data, interfaces/compatibility, authorization/privacy, state/concurrency, operations, and legal/policy effects remain unknown; Phase 4 must not be invoked by this report. | `AC-001`–`AC-008` | Claude feature-dev Phase 4 architecture, after the pending evidence-boundary decision; not invoked here. |

## Stop Check

The report stops after Phase 3 clarification and before Phase 4 architecture. It does not repeat general clarification, invoke architecture design, or create implementation tasks. Material impacts are blocked by named information gaps; none is silently accepted or marked resolved.
