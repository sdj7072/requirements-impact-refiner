# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | One-hour dashboard.response caching | A cache key that omits tenant_id could return one tenant's dashboard to another tenant. | All callers of api.dashboard.render. | Two tenants render dashboards while a shared cache entry is populated. | critical | Key every cached dashboard response by tenant_id and verify tenant isolation in tests. | detected |
| `IMP-002` | One-hour dashboard.response caching | A role change could leave authorization-sensitive dashboard content visible for up to one hour. | Tenants whose user roles or permissions change. | A role change occurs after a dashboard response has been cached. | critical | Select and implement a dashboard-cache invalidation policy for role changes. | blocked |
| `IMP-003` | One-hour dashboard.response caching | Dashboard updates could remain invisible until the TTL expires. | Tenants with dashboard changes during the cache lifetime. | dashboard.updated is published after a response has been cached. | high | Select whether dashboard.updated invalidates the affected tenant's cache entry. | blocked |
| `IMP-004` | In-memory response reuse | Concurrent callers could observe inconsistent entries or populate duplicate values. | Concurrent requests for the same tenant. | Multiple requests arrive around cache miss, expiry, or invalidation. | medium | Use a cache abstraction with atomic get/set/delete semantics and test expiry and invalidation boundaries. | detected |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Cache dashboard.response from api/dashboard.py for one hour. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Cache api/dashboard.py render results for one hour using tenant_id as part of the cache identity, while selecting an explicit invalidation policy for authorization changes and dashboard.updated events. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | render(tenant_id) returns a dashboard.response belonging to that tenant, and no cached response may be reused across tenants. | verified | api/dashboard.py accepts tenant_id and includes it in the rendered response. |
| `INV-002` | Role changes invalidate permission-sensitive cached state. | verified | cache/permission_cache.py declares that permission_cache is invalidated on role changes and links to dashboard.response. |
| `INV-003` | A published dashboard.updated event denotes that previously rendered dashboard.response data may be stale. | inferred | events/dashboard_updated.py publishes dashboard.updated and links the event to dashboard.response; concrete subscriber wiring is absent. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-004` | api/dashboard.py accepts tenant_id and includes it in the rendered response. |
| `INV-002` | `REQ-001` | `IMP-002` | cache/permission_cache.py declares that permission_cache is invalidated on role changes and links to dashboard.response. |
| `INV-003` | `REQ-001` | `IMP-003` | events/dashboard_updated.py publishes dashboard.updated and links the event to dashboard.response; concrete subscriber wiring is absent. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | detected | unknown | The supplied evidence shows tenant-scoped rendering, while the scan path only infers a cache-to-dashboard relationship; the actual new cache key does not yet exist. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | authorization/privacy | critical | blocked | unknown | The scan infers a relationship between permission_cache and dashboard.py, but no dashboard-cache invalidation implementation exists. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | state/concurrency | high | blocked | unknown | The scan infers a relationship through dashboard.updated, but no cache subscriber or invalidation operation exists. | `INV-003` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | state/concurrency | medium | detected | unknown | The scan path does not establish the concurrency semantics of the cache implementation because no cache exists yet. | `INV-001` | the pending decision | `AC-004` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which events must invalidate the one-hour tenant-scoped dashboard cache? | Invalidate on both role changes and dashboard.updated | `IMP-002`, `IMP-003` | Safest freshness and authorization behavior, with additional invalidation wiring. |
| Which events must invalidate the one-hour tenant-scoped dashboard cache? | Invalidate only on role changes | `IMP-002`, `IMP-003` | Protects permission changes, but ordinary dashboard updates may remain stale for up to one hour. |
| Which events must invalidate the one-hour tenant-scoped dashboard cache? | Use TTL only | `IMP-002`, `IMP-003` | Smallest implementation, but both permission and dashboard changes may be stale for up to one hour. |

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
| new | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Cache api/dashboard.py render results for one hour using tenant_id as part of the cache identity, while selecting an explicit invalidation policy for authorization changes and dashboard.updated events. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Given cached responses for multiple tenants, render(tenant_id) only returns the response cached for that exact tenant_id. | Required by the existing tenant_id input and tenant-bearing response. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | The selected role-change invalidation behavior is implemented and tested after priming the cache. | cache/permission_cache.py establishes role-change invalidation as current behavior. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | The selected dashboard.updated behavior is tested after priming the cache. | events/dashboard_updated.py links dashboard.updated to dashboard.response. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-001` | A response is reused before 3,600 seconds and recomputed at or after 3,600 seconds using controllable time in tests. | The requested cache lifetime is one hour. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-002` | blocked | The requested TTL does not specify whether role changes invalidate dashboard.response. | none | Requester |
| `IMP-003` | blocked | The requested TTL does not specify whether dashboard.updated invalidates the tenant cache. | none | Requester |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| api/dashboard.py response caching and tenant cache identity | The file contains render(tenant_id) and dashboard.response. | verified |
| cache/permission_cache.py role-change invalidation relationship | The file declares role-change invalidation and references dashboard.response. | verified relationship; implementation hook absent |
| events/dashboard_updated.py event-driven dashboard invalidation | The file declares dashboard.updated and references dashboard.response. | verified relationship; implementation hook absent |
| Graph paths for IMP-001 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Graph paths for IMP-002 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Graph paths for IMP-003 | PATH-002: cache/permission_cache.py → dashboard.response | PATH-002: provider builtin; confidence lexical; location cache/permission_cache.py + events/dashboard_updated.py |
| Graph paths for IMP-004 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 28327d325d776a302ed76c8cb280ebb2; sha256 b44fb1e57d147a2f6f1b77017bd34b82a64e7c2eb21be1208a62c4b3f36276f3; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Not ready |
