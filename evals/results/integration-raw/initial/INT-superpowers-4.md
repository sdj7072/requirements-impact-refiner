# Requirements Impact Report — Superpowers integration

## Original Requirement

| Requirement ID | Requirement | Evidence |
| --- | --- | --- |
| `REQ-001` | “Brainstorming approved the design; refine repository impacts next.” | Supplied integration case; Superpowers brainstorming is complete and `writing-plans` has not started. |

## Current Refined Requirement

Refine the approved brainstorming design against repository evidence, preserving existing behavior, contracts, data, permissions, operational guarantees, compatibility commitments, and regression expectations except where the approved design explicitly changes them. Return the canonical report immediately before Superpowers `writing-plans`. No implementation mechanics are selected by the supplied context.

## Current Behavior

| Invariant ID | Current behavior / invariant | Evidence level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `INV-001` | Behavior outside the approved design remains unchanged. | `unknown` | No product source, tests, or approved-design artifact supplied. | `blocked` | `must-preserve` `REQ-001` |
| `INV-002` | Existing data shape, persistence, integrity, and migration guarantees remain valid unless explicitly revised. | `unknown` | No models, schemas, migrations, or fixtures supplied. | `blocked` | `must-preserve` `REQ-001` |
| `INV-003` | Authorization, privacy, consent, and audit expectations remain valid. | `unknown` | No authorization, policy, privacy, or audit evidence supplied. | `blocked` | `must-preserve` `REQ-001` |
| `INV-004` | Existing interfaces and supported consumers remain compatible unless explicitly revised. | `unknown` | No contracts, handlers, clients, events, or compatibility tests supplied. | `blocked` | `must-preserve` `REQ-001` |

## Preserved Invariants

`INV-001` through `INV-004` must be preserved by `REQ-001`; their product evidence remains unavailable and is named in the ledger below.

## Impact Ledger

| ID | Requirement | Impact | Category | Severity | State | Evidence Level | Evidence | Invariants | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | The approved design may regress an entry point or adjacent flow. | Functionality / Regression | High | `blocked` | `unknown` | No entry points, callers, services, flags, or regression tests inspected. | `INV-001` | `AC-001` |
| `IMP-002` | `REQ-001` | The design may require unrecognized model, migration, serialization, retention, or integrity changes. | Data | High | `blocked` | `unknown` | No models, schemas, migrations, serializers, cleanup paths, or fixtures inspected. | `INV-002` | `AC-002` |
| `IMP-003` | `REQ-001` | Existing API, event, webhook, or client-consumer compatibility may be affected. | Interfaces / Compatibility | High | `blocked` | `unknown` | No contracts, DTOs, event schemas, consumers, or version tests inspected. | `INV-004` | `AC-003` |
| `IMP-004` | `REQ-001` | Changed access or visibility may alter authorization, privacy, consent, or audit behavior. | Authorization / Privacy | High | `blocked` | `unknown` | No middleware, role checks, classification, consent/deletion paths, or audit tests inspected. | `INV-003` | `AC-004` |
| `IMP-005` | `REQ-001` | Runtime state, transactions, retries, ordering, or idempotency may change. | State / Concurrency | High | `blocked` | `unknown` | No state machines, transactions, queues, retry settings, or race tests inspected. | — | `AC-005` |
| `IMP-006` | `REQ-001` | Deployment, rollout, observability, rollback, or recovery requirements may be missed. | Operations | Medium | `blocked` | `unknown` | No deployment manifests, metrics, alerts, runbooks, backups, or release checks inspected. | — | `AC-006` |
| `IMP-007` | `REQ-001` | Legal, retention, regional, or policy constraints may apply. | Legal / Policy | Medium | `blocked` | `unknown` | No policy, data inventory, retention schedule, regional rule, or approval record supplied. | — | `AC-007` |

## Decisions and Accepted Risks

No concrete `DEC-###` is recorded. The supplied approval establishes the requirement baseline and Superpowers workflow position; it does not select a migration, API transition, retry, rollout, or rollback policy. No impact is accepted.

## Requirement Revision History

| Requirement | Revision | Decision | Impact result |
| --- | --- | --- | --- |
| `REQ-001` | Preserve the approved design while refining it against repository evidence before `writing-plans`. | The pending decision | `IMP-001`–`IMP-007` remain blocked; `new: none`. |

## One focused decision

Provide the approved design’s authoritative text/path and repository scope, then choose the evidence boundary: (1) core-path inspection of entry points, callers/callees, contracts, persistence, authorization, operations, and adjacent tests; (2) repository-wide inspection; or (3) supplied-artifacts-only handoff carrying these named gaps. No option is selected, so no concrete decision ID is created.

## Whole-set recalculation

No selection or product evidence was supplied. The complete known set remains `IMP-001`–`IMP-007`; none is superseded or newly introduced.

## Delta

- resolved: none
- mitigated: none
- unchanged: none
- accepted: none
- deferred: none
- blocked: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007`
- new: none

Each known impact appears in exactly one delta category.

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Affected entry points and adjacent regression coverage or gaps are identified before planning. | `unknown`: design and source unavailable. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | Data, schema, serialization, retention, migration, and integrity impacts are identified. | `unknown`: model/schema evidence unavailable. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-004` | Affected interfaces and consumer compatibility are identified and testable. | `unknown`: contract/consumer evidence unavailable. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-003` | Access, privacy, consent, and audit behavior remain compliant or are explicit gaps. | `unknown`: authorization/policy evidence unavailable. |
| `AC-005` | `REQ-001` | `IMP-005` | — | State, transaction, retry, ordering, and idempotency behavior is preserved or explicitly revised later. | `unknown`: runtime evidence unavailable. |
| `AC-006` | `REQ-001` | `IMP-006` | — | Rollout, observability, rollback, and recovery requirements are identified. | `unknown`: operations evidence unavailable. |
| `AC-007` | `REQ-001` | `IMP-007` | — | Legal, retention, regional, and policy constraints are identified or recorded as external gaps. | `unknown`: policy evidence unavailable. |

## Unresolved, Deferred, and Blocked Items

| Impact IDs | State | Named information gap | Linked decision |
| --- | --- | --- | --- |
| `IMP-001`–`IMP-007` | `blocked` | Approved design text/identifier, repository scope, and corresponding source, contract, schema, policy, operations, and test evidence. | The pending decision |

## Analysis Scope and Limitations

Inspected the supplied Superpowers integration context and the selected adapter contract. It confirms entry after brainstorming approval and exit before `writing-plans`, but supplies no product behavior or repository artifacts; all product-specific claims therefore remain `unknown` and blocked.

## Planning Handoff

This is a report-only handoff at the Superpowers boundary: after approved `brainstorming`, before `writing-plans`. No brainstorming is repeated, no external workflow is invoked, and no implementation tasks or plan are authored. `REQ-001`, `INV-001`–`INV-004`, `IMP-001`–`IMP-007`, and `AC-001`–`AC-007` are available to the next workflow; the seven impacts require the named evidence gap or an explicit supplied-artifacts-only decision.
