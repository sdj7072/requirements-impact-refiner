# Requirements Impact Refinement Report — Superpowers integration

## Context and workflow boundary

- **Selected mode:** `superpowers`.
- **Entry:** Superpowers `brainstorming` has approved the design; repository impacts are being refined before `writing-plans` begins.
- **Exit:** This is a canonical, report-only handoff immediately before `writing-plans`. It does not repeat brainstorming, invoke `writing-plans`, or create implementation tasks.
- **Supplied evidence:** “Brainstorming approved the design; refine repository impacts next”; “Superpowers brainstorming is complete”; “writing-plans has not started.”
- **Inspection scope:** The approved design text and product repository evidence were not supplied in this handoff. Product-specific behavior and impacts therefore remain unknown rather than inferred.

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | “Brainstorming approved the design; refine repository impacts next.” | Supplied task context; Superpowers brainstorming is complete and `writing-plans` has not started. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Refine the approved brainstorming design against repository evidence and hand off a canonical impact report immediately before `writing-plans`; preserve existing behavior and explicit compatibility obligations except where the design changes them. | No decision recorded; the pending decision remains open. | none |

The brainstorming approval establishes the requirement baseline and workflow position; it does not select implementation mechanics such as a migration, API transition, retry policy, rollout, or rollback strategy. No concrete `DEC-###` is recorded.

## Requirement revision

`REQ-001` — Refine the approved brainstorming design against repository evidence, preserving existing behavior, contracts, data, permissions, operational guarantees, compatibility commitments, and regression expectations except where the approved design explicitly changes them. Return the canonical impact report to Superpowers immediately before `writing-plans`.

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | Existing user-visible and programmatic behavior outside the approved design remains unchanged. | `unknown` | No source, tests, or approved-design details were supplied. | `blocked` | `must-preserve` `REQ-001` |
| `INV-002` | Existing data shape, persistence, integrity, and migration guarantees remain valid unless the approved design explicitly revises them. | `unknown` | No models, schemas, migrations, fixtures, or design artifact were supplied. | `blocked` | `must-preserve` `REQ-001` |
| `INV-003` | Existing authorization, privacy, consent, and audit expectations remain valid. | `unknown` | No authorization, policy, privacy, or audit evidence was supplied. | `blocked` | `must-preserve` `REQ-001` |
| `INV-004` | Existing public/internal interfaces and supported consumers remain compatible unless explicitly revised by the approved design. | `unknown` | No contracts, handlers, clients, events, or compatibility tests were supplied. | `blocked` | `must-preserve` `REQ-001` |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | Existing behavior evidence is unavailable. |
| `INV-002` | `REQ-001` | `IMP-002` | Data and migration evidence is unavailable. |
| `INV-003` | `REQ-001` | `IMP-004` | Authorization and policy evidence is unavailable. |
| `INV-004` | `REQ-001` | `IMP-003` | Contract and consumer evidence is unavailable. |

## Impact Ledger

| ID | Requirement | Impact | Category | Severity | Evidence Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | The approved design may alter an entry point or adjacent flow and regress preserved behavior. | Functionality / Regression | High | `unknown` | No entry points, callers, services, feature flags, or regression tests were inspected. | `blocked` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | `REQ-001` | The design may require unrecognized model, migration, serialization, retention, or integrity changes. | Data | High | `unknown` | No models, schemas, migrations, serializers, cleanup paths, or fixtures were inspected. | `blocked` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | `REQ-001` | Existing API, event, webhook, or client-consumer compatibility may be affected. | Interfaces / Compatibility | High | `unknown` | No API contracts, DTOs, event schemas, consumers, or version tests were inspected. | `blocked` | `affects` `REQ-001`, `INV-004`; `produces` `AC-003` |
| `IMP-004` | `REQ-001` | Changed data access or visibility may alter authorization, privacy, consent, or audit behavior. | Authorization / Privacy | High | `unknown` | No middleware, role checks, data classification, consent/deletion paths, or audit tests were inspected. | `blocked` | `affects` `REQ-001`, `INV-003`; `produces` `AC-004` |
| `IMP-005` | `REQ-001` | Runtime state, transactions, retries, ordering, or idempotency may change on the affected path. | State / Concurrency | High | `unknown` | No state machines, transaction boundaries, queues, retry configuration, or race tests were inspected. | `blocked` | `affects` `REQ-001`; `produces` `AC-005` |
| `IMP-006` | `REQ-001` | Deployment, rollout, observability, rollback, or recovery requirements may be missed. | Operations | Medium | `unknown` | No deployment manifests, metrics, alerts, runbooks, backups, or release checks were inspected. | `blocked` | `affects` `REQ-001`; `produces` `AC-006` |
| `IMP-007` | `REQ-001` | Legal, retention, regional, or policy constraints may apply to the changed data or behavior. | Legal / Policy | Medium | `unknown` | No policy, data inventory, retention schedule, regional rule, or approval record was supplied. | `blocked` | `affects` `REQ-001`; `produces` `AC-007` |

## One focused evidence-gap question

Please provide the approved brainstorming design (or its authoritative path/identifier) and the repository scope to inspect. Which evidence boundary should govern the next refinement pass?

1. **Core-path inspection (recommended):** inspect the approved design’s entry points, direct callers/callees, contracts, persistence, authorization, operations, and adjacent regression tests.
2. **Repository-wide inspection:** inspect all potentially affected modules and cross-cutting policies before planning.
3. **Supplied-artifacts-only handoff:** keep repository impacts blocked and carry the named validation gaps into planning.

No option is selected in the supplied context. This is an evidence/impact-resolution question, not a selection of implementation mechanics; the pending decision remains open and no concrete `DEC-###` is recorded.

## Recorded decision

**Decision needed:** No concrete recorded decision. “Brainstorming approved the design” establishes the requirement baseline, not a repository inspection boundary or implementation policy.

## Decisions and Accepted Risks

No concrete `DEC-###` is recorded. No impact is accepted; all material impacts remain blocked by named evidence gaps.

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Preserve the approved brainstorming design while refining it against repository evidence. | none | none | `IMP-001`–`IMP-007` remain blocked; `new: none`. |

## Whole-set recalculation

No stakeholder selection or additional repository evidence was supplied. The complete known impact set remains `IMP-001` through `IMP-007`; no impact is superseded or newly introduced. All seven remain blocked by named evidence gaps.

## Delta

- **resolved:** none
- **mitigated:** none
- **unchanged:** none
- **accepted:** none
- **deferred:** none
- **blocked:** `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007`
- **new:** none

Each known impact appears in exactly one mutually exclusive delta category.

## Acceptance and Regression Criteria

| Criterion ID | Criterion | Level | Supporting evidence / gap | Links |
| --- | --- | --- | --- | --- |
| `AC-001` | Before planning relies on this report, affected entry points and preserved adjacent behavior are identified and regression coverage or gaps are explicit. | `unknown` | Requires approved-design and repository inspection; no source or tests supplied. | `produced by` `IMP-001`; `verifies` `REQ-001`, `INV-001` |
| `AC-002` | Any data, schema, serialization, retention, migration, and integrity impact is identified with its validation requirement. | `unknown` | Requires model/schema/migration/fixture evidence; unavailable here. | `produced by` `IMP-002`; `verifies` `REQ-001`, `INV-002` |
| `AC-003` | Affected interfaces and supported-consumer compatibility behavior are identified and testable. | `unknown` | Requires contracts, consumers, and compatibility evidence; unavailable here. | `produced by` `IMP-003`; `verifies` `REQ-001`, `INV-004` |
| `AC-004` | Access, privacy, consent, and audit behavior remain compliant for changed paths or are explicitly marked as gaps. | `unknown` | Requires authorization and policy evidence; unavailable here. | `produced by` `IMP-004`; `verifies` `REQ-001`, `INV-003` |
| `AC-005` | State, transaction, retry, ordering, and idempotency behavior is preserved or explicitly revised by a later recorded choice. | `unknown` | Requires runtime-path and concurrency evidence; unavailable here. | `produced by` `IMP-005`; `verifies` `REQ-001` |
| `AC-006` | Rollout, observability, rollback, and recovery requirements are identified before implementation planning. | `unknown` | Requires deployment and operations evidence; unavailable here. | `produced by` `IMP-006`; `verifies` `REQ-001` |
| `AC-007` | Applicable legal, retention, regional, and policy constraints are identified or recorded as external validation gaps. | `unknown` | Requires policy/data-inventory evidence; unavailable here. | `produced by` `IMP-007`; `verifies` `REQ-001` |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001`–`IMP-007` | `blocked` | Approved design text/identifier, repository scope, and corresponding source, contract, schema, policy, operations, and test evidence are missing. | The pending decision | Requirement owner / planning requestor |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Superpowers workflow boundary | Supplied context; `integration-superpowers.md` Entry/Ownership/Output/Exit | Confirms entry after brainstorming and exit before `writing-plans`; does not establish product behavior. |
| Product repository and approved design | No source paths, diff, approved-design artifact, contracts, schemas, policies, deployment files, or tests supplied | Product-specific impact claims remain `unknown` and blocked. |

## Planning Handoff

Refinement stops at the Superpowers adapter’s report-only boundary: after approved `brainstorming` and before `writing-plans`. The seven material impacts are blocked by named missing evidence, not silently accepted or resolved. No broad ideation is repeated, no external workflow is invoked, and no implementation work breakdown or plan is authored.

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: refine the approved brainstorming design using its authoritative text and repository evidence while preserving current behavior and explicit compatibility obligations. | `INV-001`–`INV-004`, `IMP-001`–`IMP-007` | Functionality, data, interfaces/compatibility, authorization/privacy, state/concurrency, operations, and legal/policy impacts remain unknown until the design and inspection scope are supplied. | `AC-001`–`AC-007` | Superpowers `writing-plans` is the next workflow, but it is not invoked by this report. |
