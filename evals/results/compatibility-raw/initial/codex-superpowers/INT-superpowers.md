# Requirements Impact Report — Superpowers integration

## Workflow gate

- **Entry:** satisfied after approved `brainstorming` design.
- **Ownership:** Superpowers is the sole orchestrator for this run; no other
  orchestrator or adapter is active.
- **Exit:** stop before `writing-plans`; this is a report-only handoff.

## Original Requirement

| ID | Request | Source |
| --- | --- | --- |
| `REQ-001` | Superpowers brainstorming is complete; refine repository impacts next. | Supplied task context |

The approved design is the baseline and is not reopened as ideation. Its
authoritative design text and product-repository scope were not supplied.

## Current Refined Requirement

`REQ-001`: Refine the approved brainstorming design against authoritative
repository evidence before `writing-plans`, preserving current behavior,
data, interfaces, authorization/privacy, runtime guarantees, operations,
compatibility, and policy obligations except where the approved design
explicitly changes them.

No design-specific mechanic is selected. This wording is a requirement
baseline, not an implementation plan.

## Preserved Invariants

| ID | Invariant | Evidence |
| --- | --- | --- |
| `INV-001` | Existing behavior outside the approved change remains unchanged. | No product source, tests, or design text supplied (`unknown`). |
| `INV-002` | Existing data shape, persistence, integrity, and migration guarantees remain valid unless explicitly revised. | No models, schemas, migrations, serializers, or fixtures supplied (`unknown`). |
| `INV-003` | Existing authorization, privacy, consent, and audit expectations remain valid. | No policy, middleware, role, or audit evidence supplied (`unknown`). |
| `INV-004` | Existing public/internal interfaces and supported consumers remain compatible unless explicitly revised. | No contracts, handlers, events, clients, or compatibility tests supplied (`unknown`). |

## Impact Ledger

| ID | Impact | Category | Severity | State | Evidence | Invariants | Decision | Acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | The design may alter an entry point or adjacent flow and regress preserved behavior. | Functionality / Regression | High | `blocked` | `unknown`: no entry points, callers, flags, or regression tests inspected. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | The design may require unrecognized model, migration, serialization, retention, or integrity changes. | Data | High | `blocked` | `unknown`: no data or persistence evidence inspected. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | Existing API, event, webhook, or client-consumer compatibility may be affected. | Interfaces / Compatibility | High | `blocked` | `unknown`: no contracts, consumers, or version tests inspected. | `INV-004` | the pending decision | `AC-003` |
| `IMP-004` | Changed access or visibility may alter authorization, privacy, consent, or audit behavior. | Authorization / Privacy | High | `blocked` | `unknown`: no access-control or policy evidence inspected. | `INV-003` | the pending decision | `AC-004` |
| `IMP-005` | Runtime state, transactions, retries, ordering, or idempotency may change. | State / Concurrency | High | `blocked` | `unknown`: no runtime or concurrency evidence inspected. | none | the pending decision | `AC-005` |
| `IMP-006` | Deployment, rollout, observability, rollback, or recovery requirements may be missed. | Operations | Medium | `blocked` | `unknown`: no deployment or operations evidence inspected. | none | the pending decision | `AC-006` |
| `IMP-007` | Legal, retention, regional, or policy constraints may apply. | Legal / Policy | Medium | `blocked` | `unknown`: no policy or data-inventory evidence supplied. | none | the pending decision | `AC-007` |

## Focused evidence-gap question

Please provide the approved design (or authoritative path/identifier) and
choose one inspection boundary:

1. **Core-path inspection (recommended):** entry points, direct callers and
   callees, contracts, persistence, authorization, operations, and adjacent
   regression tests.
2. **Repository-wide inspection:** all potentially affected modules and
   cross-cutting policies.
3. **Supplied-artifacts-only handoff:** keep product impacts blocked and carry
   the named validation gaps forward.

This asks only for evidence scope; it does not select implementation policy.
No option has been selected, so no concrete `DEC-###` is recorded.

## Acceptance and Regression Criteria

| ID | Criterion | Supporting evidence needed |
| --- | --- | --- |
| `AC-001` | Affected entry points and preserved adjacent behavior are identified with regression coverage or explicit gaps. | Design, source, and test inspection. |
| `AC-002` | Data, schema, serialization, retention, migration, and integrity impacts are testable. | Model/schema/migration/fixture inspection. |
| `AC-003` | Affected interfaces and supported-consumer compatibility behavior are identified and testable. | Contract/consumer/version inspection. |
| `AC-004` | Changed access, privacy, consent, and audit behavior is compliant or explicitly a gap. | Authorization and policy inspection. |
| `AC-005` | State, transaction, retry, ordering, and idempotency behavior is preserved or explicitly revised by a recorded choice. | Runtime/concurrency inspection. |
| `AC-006` | Rollout, observability, rollback, and recovery requirements are identified before planning. | Deployment/operations inspection. |
| `AC-007` | Legal, retention, regional, and policy constraints are identified or recorded as external gaps. | Policy/data-inventory inspection. |

## Decision, delta, and limitations

**Decision needed:** the inspection-boundary decision remains open. No impact
is accepted, resolved, or deferred by silence; no `DEC-###` is created.

Complete current-set delta:

- resolved: none
- mitigated: none
- unchanged: none
- accepted: none
- deferred: none
- blocked: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007`
- new: none

The product-specific impacts remain `unknown` because no design artifact,
repository scope, source, contracts, schemas, policies, operations files, or
tests were supplied. Each known impact appears in exactly one delta category.

## Planning Handoff

Refinement stops after approved Superpowers `brainstorming` and before
`writing-plans`. The refined requirement, evidence gaps, impacts, and
acceptance criteria are ready for the next planning step once the requested
design and inspection boundary are supplied. `writing-plans` is not invoked
here, and no work breakdown is authored.

| Requirement | Reports | Remaining risks | Criteria | Next workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `INV-001`–`INV-004`, `IMP-001`–`IMP-007` | Functionality, data, interfaces/compatibility, authorization/privacy, state/concurrency, operations, and legal/policy evidence gaps. | `AC-001`–`AC-007` | Superpowers `writing-plans` (not invoked) |
