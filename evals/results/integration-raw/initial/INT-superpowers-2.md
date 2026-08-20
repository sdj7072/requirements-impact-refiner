# Requirements Impact Report — Superpowers integration

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Brainstorming approved the design; refine repository impacts next. | Supplied task context; Superpowers brainstorming is complete and `writing-plans` has not started. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Refine the approved brainstorming design against authoritative repository evidence before `writing-plans`, preserving existing behavior, data, interfaces, authorization/privacy, runtime guarantees, operations, compatibility, and policy obligations except where the approved design explicitly changes them. | Decision needed; no recorded decision | none |

The approved brainstorming result is the requirement baseline and workflow position. It does not select a migration, API transition, retry, rollout, rollback, or other implementation mechanic. The exact approved design artifact and product repository scope were not supplied.

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Existing user-visible and programmatic behavior outside the approved change remains unchanged. | `unknown` | No product source, tests, or approved-design details supplied. |
| `INV-002` | Existing data shape, persistence, integrity, and migration guarantees remain valid unless explicitly revised by the approved design. | `unknown` | No models, schemas, migrations, serializers, or fixtures supplied. |
| `INV-003` | Existing authorization, privacy, consent, and audit expectations remain valid. | `unknown` | No middleware, role checks, policy, privacy, or audit evidence supplied. |
| `INV-004` | Existing public/internal interfaces and supported consumers remain compatible unless explicitly revised. | `unknown` | No contracts, handlers, clients, events, or compatibility tests supplied. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | Product behavior and regression evidence unavailable. |
| `INV-002` | `REQ-001` | `IMP-002` | Data and migration evidence unavailable. |
| `INV-003` | `REQ-001` | `IMP-004` | Authorization and policy evidence unavailable. |
| `INV-004` | `REQ-001` | `IMP-003` | Contract and consumer evidence unavailable. |

## Impact Ledger

| ID | Requirement | Impact | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | The approved design may alter an entry point or adjacent flow and regress preserved behavior. | Functionality / Regression | High | `blocked` | `unknown` | No entry points, callers, services, flags, or regression tests inspected. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | The design may require unrecognized model, migration, serialization, retention, or integrity changes. | Data | High | `blocked` | `unknown` | No models, schemas, migrations, serializers, cleanup paths, or fixtures inspected. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | Existing API, event, webhook, or client-consumer compatibility may be affected. | Interfaces / Compatibility | High | `blocked` | `unknown` | No API contracts, DTOs, event schemas, consumers, or version tests inspected. | `INV-004` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | Changed access or visibility may alter authorization, privacy, consent, or audit behavior. | Authorization / Privacy | High | `blocked` | `unknown` | No middleware, role checks, classification, consent/deletion paths, or audit tests inspected. | `INV-003` | the pending decision | `AC-004` |
| `IMP-005` | `REQ-001` | Runtime state, transactions, retries, ordering, or idempotency may change on the affected path. | State / Concurrency | High | `blocked` | `unknown` | No state machines, transaction boundaries, queues, retry configuration, or race tests inspected. | none | the pending decision | `AC-005` |
| `IMP-006` | `REQ-001` | Deployment, rollout, observability, rollback, or recovery requirements may be missed. | Operations | Medium | `blocked` | `unknown` | No deployment manifests, metrics, alerts, backups, runbooks, or release checks inspected. | none | the pending decision | `AC-006` |
| `IMP-007` | `REQ-001` | Legal, retention, regional, or policy constraints may apply to changed data or behavior. | Legal / Policy | Medium | `blocked` | `unknown` | No policy, data inventory, retention schedule, regional rule, or approval record supplied. | none | the pending decision | `AC-007` |

## One Focused Evidence-Gap Question

Please provide the approved design (or authoritative path/identifier) and choose the inspection boundary for the next pass:

1. **Core-path inspection (recommended):** inspect the design’s entry points, direct callers/callees, contracts, persistence, authorization, operations, and adjacent regression tests.
2. **Repository-wide inspection:** inspect all potentially affected modules and cross-cutting policies.
3. **Supplied-artifacts-only handoff:** keep product impacts blocked and carry the named validation gaps forward.

This resolves an evidence boundary, not an implementation policy. No option is selected in the supplied context; no concrete `DEC-###` is created.

## Recorded Decision

**Decision needed:** the pending inspection-boundary decision remains open. No impact is accepted, resolved, or deferred by silence.

## Decisions and Accepted Risks

No concrete `DEC-###` is recorded because the supplied context contains no stakeholder selection. No impact is accepted; the seven material impacts remain blocked by named evidence gaps.

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Preserve the approved brainstorming design while refining it against repository evidence before `writing-plans`. | none; the pending decision remains open | none | `IMP-001`–`IMP-007` remain blocked; `new: none` |

## Whole-Set Recalculation

No stakeholder selection, approved-design artifact, or product repository evidence was supplied. The complete known set remains `IMP-001`–`IMP-007`; none is superseded and no new impact is identified.

## Delta

- resolved: none
- mitigated: none
- unchanged: none
- accepted: none
- deferred: none
- blocked: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007`
- new: none

Each known impact appears in exactly one delta category. The ledger’s blocked state is therefore represented only under `blocked`.

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Affected entry points and preserved adjacent behavior are identified, with regression coverage or gaps explicit. | Approved-design and repository/test inspection required; unavailable. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | Every data, schema, serialization, retention, migration, and integrity impact has a validation requirement. | Model/schema/migration/fixture inspection required; unavailable. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-004` | Affected interfaces and supported-consumer compatibility behavior are identified and testable. | Contract/consumer/version inspection required; unavailable. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-003` | Access, privacy, consent, and audit behavior for changed paths is compliant or explicitly a gap. | Authorization/policy inspection required; unavailable. |
| `AC-005` | `REQ-001` | `IMP-005` | none | State, transaction, retry, ordering, and idempotency behavior is preserved or explicitly revised by a later recorded choice. | Runtime/concurrency inspection required; unavailable. |
| `AC-006` | `REQ-001` | `IMP-006` | none | Rollout, observability, rollback, and recovery requirements are identified before planning. | Deployment/operations inspection required; unavailable. |
| `AC-007` | `REQ-001` | `IMP-007` | none | Applicable legal, retention, regional, and policy constraints are identified or recorded as external gaps. | Policy/data-inventory inspection required; unavailable. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001`–`IMP-007` | `blocked` | The approved design, repository scope, and corresponding source, contract, schema, policy, operations, and test evidence are missing. | the pending decision | Requirement owner / planning requestor |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Superpowers workflow boundary | Supplied context and `integration-superpowers.md` Entry/Ownership/Output/Exit | Confirms entry after brainstorming and exit before `writing-plans`; does not establish product behavior. |
| Product repository and approved design | No source paths, diff, design artifact, contracts, schemas, policies, deployment files, or tests supplied | Product-specific impacts remain `unknown` and blocked. |

## Planning Handoff

Refinement stops at the Superpowers report-only boundary: after approved `brainstorming` and before `writing-plans`. The report does not repeat ideation, invoke an external workflow, or create an implementation work breakdown.

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: refine the approved brainstorming design using its authoritative text and repository evidence while preserving current behavior and explicit compatibility obligations. | `INV-001`–`INV-004`, `IMP-001`–`IMP-007` | Functionality, data, interfaces/compatibility, authorization/privacy, state/concurrency, operations, and legal/policy impacts remain blocked pending named evidence. | `AC-001`–`AC-007` | Superpowers `writing-plans` is next, but is not invoked by this report. |
