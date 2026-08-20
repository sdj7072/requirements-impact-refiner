# Requirements Impact Report — POS-cache

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Cache the dashboard response for one hour. | Supplied request. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Keep a one-hour maximum TTL; key responses by tenant and authorization context; invalidate entries on both `dashboard.updated` and role changes. Defer broader cache redesign. | `DEC-001` | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Dashboard results depend on `tenant_id`; results must not cross tenant boundaries. | `verified` | Supplied repository evidence: dashboard results depend on `tenant_id`. |
| `INV-002` | Role changes invalidate `permission_cache` only. | `verified` | Supplied repository evidence: role changes invalidate `permission_cache` only. |
| `INV-003` | Dashboard writes publish `dashboard.updated`. | `verified` | Supplied repository evidence: dashboard writes publish `dashboard.updated`. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | Supplied tenant dependency. |
| `INV-002` | `REQ-001` | `IMP-003` | Supplied permission-cache behavior. |
| `INV-003` | `REQ-001` | `IMP-002` | Supplied dashboard event behavior. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Data / Authorization | Critical | `mitigated` | `verified` | Tenant-dependent results require tenant isolation; `DEC-001` requires tenant-scoped keys and authorization context. | `INV-001` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | State / Interfaces | High | `mitigated` | `verified` | `dashboard.updated` is published; `DEC-001` requires invalidation on that event. | `INV-003` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | Authorization / Privacy | Critical | `mitigated` | `verified` | Role changes currently invalidate only `permission_cache`; `DEC-001` requires dashboard-cache invalidation on role changes and authorization-context keying. | `INV-002` | `DEC-001` | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | “Keep the one-hour TTL, key by tenant and authorization context, and invalidate on both dashboard.updated and role changes. Defer any broader cache redesign.” | `REQ-001` | — | Explicit stakeholder selection; preserves tenant isolation and bounds freshness after dashboard writes and role changes while deferring unrelated redesign. |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Initial request: cache dashboard response for one hour. | — | — | `IMP-001`, `IMP-002`, `IMP-003` detected. |
| `REQ-001` | One-hour maximum TTL, tenant + authorization-context key, invalidation on `dashboard.updated` and role changes; broader redesign deferred. | `DEC-001` | — | `IMP-001`, `IMP-002`, `IMP-003` mitigated. |

## Whole-Set Recalculation

Every known impact was re-evaluated after `DEC-001`:

- `resolved: none`
- `mitigated: IMP-001, IMP-002, IMP-003`
- `unchanged: none`
- `accepted: none`
- `deferred: none`
- `blocked: none`
- `new: none`

The deferred broader cache redesign is a scope choice, not a known impact or silent acceptance.

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | A cached response is never returned across tenants; cache identity includes `tenant_id` and the required authorization context. | Supplied tenant dependency; add cross-tenant and authorization-context cache-isolation coverage during implementation. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | Publishing `dashboard.updated` invalidates affected dashboard responses before a subsequent read can use the old entry. | Supplied event behavior; add event-to-invalidation regression coverage. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-002` | A role change invalidates affected dashboard responses, and no response is served under the prior authorization context. | Supplied role-change behavior; add role-change/dashboard-cache regression coverage. |
| `AC-004` | `REQ-001` | `IMP-001` | `INV-001` | Entries expire no later than one hour after insertion when no invalidation occurs. | Requirement target; TTL boundary test remains implementation validation. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| — | — | No material impact remains unresolved after `DEC-001`; implementation evidence and regression tests are still required for resolution. | `DEC-001` | Planning/implementation owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Analysis used the supplied repository facts only; no implementation plan or code changes were made. | `tenant_id`, `permission_cache`, and `dashboard.updated` facts supplied with POS-cache. | Impacts and invariants are verified against supplied evidence. Mitigation is requirement-level; implementation must prove the acceptance criteria. |
| Broader cache redesign was explicitly deferred. | Selection recorded in `DEC-001`. | No conclusions are made about cache architecture outside this one-hour dashboard behavior. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: one-hour maximum TTL, tenant + authorization-context keys, invalidation on `dashboard.updated` and role changes; broader redesign deferred. | `REQ-001`, `INV-001`–`INV-003`, `IMP-001`–`IMP-003`, `DEC-001` | Implementation may fail to wire one invalidation path or omit an authorization dimension; verify `AC-001`–`AC-004`. | `AC-001`–`AC-004` | Superpowers planning handoff; proceed to `writing-plans` only after this report. |

**Status: DONE.**

---

## Pre-decision record

The preceding `POS-cache.md.part1` contains the initial ledger and the focused options presented before selection. `DEC-001` above is the explicit response and supersedes the pending-decision state; all known impacts are recalculated in the complete report above.
