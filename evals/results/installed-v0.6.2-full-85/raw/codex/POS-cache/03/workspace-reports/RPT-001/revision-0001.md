# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | One-hour dashboard response cache | A user may receive dashboard content authorized under stale roles. | Tenants and users whose roles change while a response is cached. | A role change before the 3,600-second TTL expires. | critical | Invalidate the affected tenant's dashboard cache when role-change invalidation runs and keep cache keys tenant-scoped. | mitigated |
| `IMP-002` | One-hour dashboard response cache | Updated dashboard data can remain invisible until TTL expiry. | Tenants with dashboard updates during the cache window. | dashboard.updated is handled before the cached entry expires. | high | Invalidate the affected tenant's cached response when dashboard.updated is handled. | mitigated |
| `IMP-003` | Tenant-scoped dashboard response cache | A cache key that omits tenant_id can return one tenant's response to another tenant. | All dashboard tenants. | Requests from different tenants share a cache entry. | critical | Key every cached response by tenant_id and test cross-tenant isolation. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Cache dashboard.response from api/dashboard.py for one hour. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Cache api/dashboard.py's dashboard.response render result for 3,600 seconds, keyed by tenant_id. Preserve tenant isolation and invalidate affected cached dashboard responses when permissions change or dashboard.updated is handled so cached authorization-sensitive content is not served stale. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Dashboard responses remain tenant-specific and identify the requested tenant. | verified | api/dashboard.py render(tenant_id) returns a response containing the supplied tenant_id. |
| `INV-002` | Role changes invalidate authorization-sensitive cached state. | verified | cache/permission_cache.py declares permission_cache invalidation on role changes and references dashboard.response. |
| `INV-003` | dashboard.updated is the signal that dashboard.response content has changed. | verified | events/dashboard_updated.py publishes dashboard.updated and links it to dashboard.response. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | api/dashboard.py render(tenant_id) returns a response containing the supplied tenant_id. |
| `INV-002` | `REQ-001` | `IMP-001` | cache/permission_cache.py declares permission_cache invalidation on role changes and references dashboard.response. |
| `INV-003` | `REQ-001` | `IMP-002` | events/dashboard_updated.py publishes dashboard.updated and links it to dashboard.response. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | mitigated | unknown | The scan connects cache/permission_cache.py to api/dashboard.py, but the graph provider was unavailable; supplied evidence indicates role-change invalidation is authorization-relevant. | `INV-002`, `INV-001` | `DEC-002` | `AC-003`, `AC-002` |
| `IMP-002` | `REQ-001` | state/concurrency | high | mitigated | unknown | The scan connects cache/permission_cache.py to events/dashboard_updated.py, but the graph provider was unavailable; supplied evidence identifies dashboard.updated as the response update signal. | `INV-003`, `INV-001` | `DEC-002` | `AC-004`, `AC-001` |
| `IMP-003` | `REQ-001` | data | critical | mitigated | unknown | The scan path includes api/dashboard.py, but the graph provider was unavailable; direct inspection shows render is tenant-specific. | `INV-001` | `DEC-001` | `AC-002` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Use a tenant_id-keyed cache with a 3,600-second TTL. | `REQ-001` | `IMP-003` | The user explicitly requested one-hour caching, and repository evidence states rendering is by tenant_id. |
| `DEC-002` | Invalidate affected dashboard cache entries on role changes and dashboard.updated handling. | `REQ-001` | `IMP-001`, `IMP-002` | The supplied invalidation and event evidence identifies both freshness boundaries; proactive invalidation preserves authorization and dashboard update behavior within the TTL. |

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
| new | `IMP-001`, `IMP-002`, `IMP-003` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Cache api/dashboard.py's dashboard.response render result for 3,600 seconds, keyed by tenant_id. Preserve tenant isolation and invalidate affected cached dashboard responses when permissions change or dashboard.updated is handled so cached authorization-sensitive content is not served stale. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-002` | `INV-003` | Absent invalidation, a cached tenant response is reused before 3,600 seconds and recomputed at or after expiry. | Required verification for the requested one-hour TTL. |
| `AC-002` | `REQ-001` | `IMP-003` | `INV-001` | Requests for different tenant_id values never share cached dashboard responses. | Required verification because the current render contract is tenant-specific. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-002` | Role-change invalidation removes the affected tenant's cached dashboard response before the next render. | Required verification from cache/permission_cache.py's existing role-change behavior. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-003` | Handling dashboard.updated removes the affected tenant's cached response before the next render. | Required verification from events/dashboard_updated.py's update signal. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| api/dashboard.py dashboard.response rendering and its tenant_id cache key | Direct repository file inspection. | high |
| Role-change invalidation integration in cache/permission_cache.py | The file declares role-change invalidation and references dashboard.response, but contains no existing callable hook. | medium |
| dashboard.updated invalidation integration in events/dashboard_updated.py | The file declares the event and response link, but contains no event payload or subscriber framework. | medium |
| Graph paths for IMP-001 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Graph paths for IMP-002 | PATH-002: cache/permission_cache.py → dashboard.response | PATH-002: provider builtin; confidence lexical; location cache/permission_cache.py + events/dashboard_updated.py |
| Graph paths for IMP-003 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt c3018fcd7549c53204e1f93a13002d86; sha256 b73ae2e8cda9a78b62e8a17e96899bd27229ae241bf129a4f43f2ca705a01a26; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001`, `DEC-002` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Ready: implement the tenant-scoped TTL cache and explicit invalidation hooks, then verify TTL, tenant isolation, role-change invalidation, and dashboard.updated invalidation. |
