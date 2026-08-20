# Integration baseline — requirements impact refinement

## Requirement revision

`REQ-001` — Implement the stakeholder-approved design from the brainstorming outcome, while preserving all existing repository behavior, contracts, data, permissions, operational guarantees, and compatibility commitments except where the approved design explicitly changes them. Repository impacts must be refined from inspected evidence before implementation planning.

Evidence: supplied task context (“Brainstorming approved the design; refine repository impacts next”). The approved design details and repository contents were not supplied for this baseline.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Links |
| --- | --- | --- | --- | --- |
| `INV-001` | Existing user-visible and programmatic behavior outside the explicitly approved change remains unchanged. | `unknown` | Repository was not inspected in this baseline; exact behavior requires targeted inspection. | `must-preserve` `REQ-001` |
| `INV-002` | Existing data shape, persistence, and migration guarantees remain valid unless the approved design explicitly revises them. | `unknown` | No models, schemas, migrations, or fixtures were inspected. | `must-preserve` `REQ-001` |
| `INV-003` | Existing authorization, privacy, and audit expectations remain valid. | `unknown` | No auth, permission, privacy, or audit evidence was inspected. | `must-preserve` `REQ-001` |
| `INV-004` | Existing public/internal interfaces and supported consumers remain compatible unless explicitly revised by the approved design. | `unknown` | No contracts, handlers, clients, or compatibility tests were inspected. | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Category | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | The approved design may alter an existing entry point or adjacent flow, causing behavioral regression outside the intended scope. | Functionality / Regression | `unknown` | No entry points, feature flags, services, or tests inspected. | `blocked` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | The approved design may require data-model, migration, serialization, retention, or integrity changes that are not yet identified. | Data | `unknown` | No models, schemas, migrations, serializers, or cleanup paths inspected. | `blocked` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | Existing API, event, webhook, or client-consumer contracts may be affected. | Interfaces / Compatibility | `unknown` | No API contracts, events, DTOs, consumers, or version tests inspected. | `blocked` | `affects` `REQ-001`, `INV-004`; `produces` `AC-003` |
| `IMP-004` | Authorization, privacy, consent, or audit behavior may need review if the design changes data access or visibility. | Authorization/Privacy | `unknown` | No middleware, role checks, audit paths, or policy evidence inspected. | `blocked` | `affects` `REQ-001`, `INV-003`; `produces` `AC-004` |
| `IMP-005` | Concurrency, transaction, retry, ordering, or idempotency behavior may be affected by the design’s runtime path. | State/Concurrency | `unknown` | No state machines, transaction boundaries, queues, or race tests inspected. | `blocked` | `affects` `REQ-001`; `produces` `AC-005` |
| `IMP-006` | Deployment, rollout, observability, rollback, or recovery procedures may require changes. | Operations | `unknown` | No deployment manifests, metrics, alerts, or runbooks inspected. | `blocked` | `affects` `REQ-001`; `produces` `AC-006` |
| `IMP-007` | Legal, policy, or regional constraints may apply to changed data or behavior. | Legal/Policy | `unknown` | No policy, data inventory, retention, or approval evidence inspected. | `blocked` | `affects` `REQ-001`; `produces` `AC-007` |

## One focused decision

The repository evidence needed to refine the ledger is unavailable in this baseline. Which inspection boundary should govern the next refinement pass?

1. **Core-path inspection (recommended)** — inspect only the approved design’s entry points, direct callers/callees, contracts, persistence, authorization, operations, and adjacent regression tests.
2. **Repository-wide inspection** — inspect all potentially affected modules and cross-cutting policies before planning.
3. **Supplied-artifacts-only handoff** — keep repository impacts blocked and hand the approved design to planning with explicit validation gaps.

No stakeholder selection is recorded; therefore no concrete `DEC-###` is created. The pending decision is required before blocked impacts can be refined or accepted.

## Recorded decision

None. The pending decision above remains open.

## Whole-set recalculation

No decision was made, so the complete known impact set remains unchanged: `IMP-001` through `IMP-007`. No impact is resolved, mitigated, accepted, deferred, or superseded by this baseline.

## Delta

- resolved: none
- mitigated: none
- unchanged: none
- accepted: none
- deferred: none
- blocked: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007`
- new: none

## Stop check and planning handoff

This is a report-only baseline, not an implementation plan or work breakdown. Planning may proceed only after the pending inspection-boundary decision and evidence collection, or may explicitly carry the named gaps as blocked.

Acceptance targets for the next refinement/validation pass:

| ID | Criterion | Supporting evidence or gap |
| --- | --- | --- |
| `AC-001` | The approved change does not regress preserved adjacent behavior. | Requires entry-point and regression-test inspection; currently unavailable. |
| `AC-002` | Any data/schema/serialization change is identified with migration and integrity expectations. | Requires model, schema, migration, and fixture inspection; currently unavailable. |
| `AC-003` | Affected interfaces and compatibility behavior are explicitly identified and tested. | Requires contract and consumer inspection; currently unavailable. |
| `AC-004` | Access, privacy, and audit behavior remain compliant for changed paths. | Requires authorization and policy inspection; currently unavailable. |
| `AC-005` | Runtime state, retries, ordering, and idempotency behavior are preserved or explicitly revised. | Requires concurrency-path inspection; currently unavailable. |
| `AC-006` | Rollout, observability, rollback, and recovery requirements are identified. | Requires operations evidence; currently unavailable. |
| `AC-007` | Applicable legal/policy constraints are identified or recorded as an external validation gap. | Requires policy/data-inventory evidence; currently unavailable. |
