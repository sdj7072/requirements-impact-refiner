# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | One-hour caching of dashboard.response | A user whose role changes could receive an authorization-stale dashboard until TTL expiry. | Users and tenants whose dashboard visibility depends on roles. | A role changes while a tenant dashboard response is cached. | critical | Invalidate the affected tenant's dashboard cache from the existing role-change invalidation path, or explicitly accept the stale-access window. | blocked |
| `IMP-002` | One-hour caching of dashboard.response | Dashboard updates could remain invisible for up to one hour. | Readers of an updated tenant dashboard. | dashboard.updated is published while that tenant's response is cached. | high | Evict the affected tenant's entry when dashboard.updated is handled, or explicitly accept TTL-only freshness. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Cache dashboard.response from api/dashboard.py for one hour. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Cache api/dashboard.py render results for 3,600 seconds using tenant_id as the cache key. Preserve tenant isolation and define explicit invalidation for permission role changes and dashboard.updated events so cached dashboard.response data cannot remain visible after authorization or dashboard content changes. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | A dashboard response rendered for one tenant must never be returned for another tenant. | verified | api/dashboard.py render(tenant_id) places tenant_id in the returned dashboard.response payload. |
| `INV-002` | Role changes must continue to invalidate permission-sensitive cached behavior. | verified | cache/permission_cache.py declares INVALIDATED_ON_ROLE_CHANGE = True and references dashboard.response. |
| `INV-003` | A dashboard.updated event must make subsequent dashboard reads observe the updated dashboard. | verified | events/dashboard_updated.py declares the dashboard.updated event and links it to dashboard.response. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | api/dashboard.py render(tenant_id) places tenant_id in the returned dashboard.response payload. |
| `INV-002` | `REQ-001` | `IMP-001` | cache/permission_cache.py declares INVALIDATED_ON_ROLE_CHANGE = True and references dashboard.response. |
| `INV-003` | `REQ-001` | `IMP-002` | events/dashboard_updated.py declares the dashboard.updated event and links it to dashboard.response. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | blocked | unknown | The receipt finds only lexical/structural-inferred linkage and reports providers unavailable; the exact invalidation wiring between cache/permission_cache.py and api/dashboard.py remains unverified. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | state/concurrency | high | blocked | unknown | The receipt finds only lexical/structural-inferred linkage and reports providers unavailable; the exact dashboard.updated consumer/invalidation wiring remains unverified. | `INV-001`, `INV-003` | the pending decision | `AC-002`, `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which invalidation policy should the one-hour dashboard cache use? | Invalidate per tenant on both role changes and dashboard.updated (recommended) | `IMP-001`, `IMP-002` | Strongest correctness and tenant isolation; requires wiring both existing invalidation signals to the new cache. |
| Which invalidation policy should the one-hour dashboard cache use? | Invalidate only on dashboard.updated | `IMP-001`, `IMP-002` | Keeps content fresh but can expose authorization-stale dashboards for up to one hour after role changes. |
| Which invalidation policy should the one-hour dashboard cache use? | Use TTL only | `IMP-001`, `IMP-002` | Smallest implementation, but accepts up to one hour of stale permissions and dashboard content. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | none |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | `IMP-001`, `IMP-002` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Cache api/dashboard.py render results for 3,600 seconds using tenant_id as the cache key. Preserve tenant isolation and define explicit invalidation for permission role changes and dashboard.updated events so cached dashboard.response data cannot remain visible after authorization or dashboard content changes. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | After a role change for a tenant, the next dashboard render for that tenant is recomputed rather than served from the previous cache entry. | Requires a focused test connecting the role-change invalidation path to the tenant dashboard cache. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | After dashboard.updated for a tenant, the next dashboard render for that tenant is recomputed. | Requires a focused event invalidation test for the tenant-scoped cache key. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-003` | Without invalidation, a cached tenant response expires after 3,600 seconds and is then recomputed. | Requires a clock-controlled TTL boundary test. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | Implementation depends on the selected invalidation policy and exact invalidation wiring. | none | Requester |
| `IMP-002` | blocked | Implementation depends on the selected invalidation policy and exact event wiring. | none | Requester |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| api/dashboard.py | Defines dashboard.response and render(tenant_id). | verified |
| cache/permission_cache.py | Defines role-change invalidation behavior and references dashboard.response. | verified |
| events/dashboard_updated.py | Defines dashboard.updated and links it to dashboard.response. | verified |
| Graph paths for IMP-001 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Graph paths for IMP-002 | PATH-002: cache/permission_cache.py → dashboard.response | PATH-002: provider builtin; confidence lexical; location cache/permission_cache.py + events/dashboard_updated.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 826a54eabf961af11f7641ee66575497; sha256 126fd31bc5d59e956229b098dee930dc6a3f0ea5fdf3fd0ffdf38ae6a405300a; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002`, `AC-003` | Not ready |
