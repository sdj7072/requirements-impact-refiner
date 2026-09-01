# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Tenant dashboard responses are cached for one hour. | A user could receive a dashboard response based on permissions that were revoked or changed. | Users whose tenant roles change while a cached dashboard response exists. | Role-change invalidation of permission_cache. | critical | Invalidate the corresponding tenant dashboard cache entry as part of the role-change path. | mitigated |
| `IMP-002` | Dashboard responses may be served from cache for one hour. | Dashboard changes may remain invisible until TTL expiry. | Tenants with a cached response when dashboard.updated is published. | Publication of dashboard.updated. | high | Evict the affected tenant dashboard cache entry when the update event is handled. | mitigated |
| `IMP-003` | Rendered dashboard responses are reused across requests. | An insufficient cache key could return one tenant's response to another tenant. | All dashboard tenants. | A cache lookup for tenants with colliding or shared keys. | critical | Use tenant_id as the complete cache identity and test isolation explicitly. | mitigated |
| `IMP-004` | Repeated renders for a tenant reuse a cached response. | Incorrect expiry semantics could cache forever or miss the requested performance benefit. | All dashboard callers. | Repeated calls before and after the one-hour boundary. | medium | Use a monotonic expiry of 3,600 seconds and test hit and expiry behavior. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Cache dashboard.response from api/dashboard.py for one hour. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Cache api/dashboard.py render results for 3,600 seconds using tenant_id as the cache key. Preserve the existing dashboard.response payload. Invalidate the affected dashboard cache entries when role changes invalidate permission_cache and when dashboard.updated is published, so authorization and dashboard-content changes are not hidden by the TTL. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Dashboard responses remain isolated by tenant_id and retain the existing {tenant, body} shape. | verified | api/dashboard.py render(tenant_id) returns a tenant-specific dictionary with body dashboard.response. |
| `INV-002` | Role changes must not leave a dashboard response reflecting obsolete permissions. | inferred | cache/permission_cache.py declares role-change invalidation and references dashboard.response. |
| `INV-003` | A dashboard.updated event must make subsequently rendered dashboard content current. | inferred | events/dashboard_updated.py publishes dashboard.updated and references dashboard.response. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-003`, `IMP-004` | api/dashboard.py render(tenant_id) returns a tenant-specific dictionary with body dashboard.response. |
| `INV-002` | `REQ-001` | `IMP-001` | cache/permission_cache.py declares role-change invalidation and references dashboard.response. |
| `INV-003` | `REQ-001` | `IMP-002` | events/dashboard_updated.py publishes dashboard.updated and references dashboard.response. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | mitigated | unknown | PATH-001 textually and structurally links cache/permission_cache.py and api/dashboard.py, but optional providers were unavailable; a one-hour cache could otherwise outlive a role change. | `INV-002` | `DEC-001` | `AC-003` |
| `IMP-002` | `REQ-001` | state/concurrency | high | mitigated | unknown | PATH-002 textually and structurally links cache/permission_cache.py and events/dashboard_updated.py, but optional providers were unavailable. | `INV-003` | `DEC-001` | `AC-004` |
| `IMP-003` | `REQ-001` | data | critical | mitigated | unknown | PATH-001 reaches the tenant-scoped dashboard renderer with lexical and structural evidence only; caching must preserve that partition. | `INV-001` | `DEC-001` | `AC-001` |
| `IMP-004` | `REQ-001` | functionality | medium | mitigated | unknown | PATH-001 reaches api/dashboard.py with lexical and structural evidence only; the requested cache introduces expiry semantics. | `INV-001` | `DEC-001` | `AC-002` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Use a tenant-scoped 3,600-second cache and make both role changes and dashboard.updated coherence boundaries. | `REQ-001` | none | The user selected a one-hour cache, the renderer is tenant-scoped, and the supplied role-change and dashboard-update evidence identifies the two paths whose freshness must override the TTL. |

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
| `REQ-001` | Cache api/dashboard.py render results for 3,600 seconds using tenant_id as the cache key. Preserve the existing dashboard.response payload. Invalidate the affected dashboard cache entries when role changes invalidate permission_cache and when dashboard.updated is published, so authorization and dashboard-content changes are not hidden by the TTL. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-003` | `INV-001` | Two tenant IDs never share cached dashboard responses, and the response schema remains unchanged. | Verify with tests that render calls for distinct tenant IDs return their own tenant values and dashboard.response body. |
| `AC-002` | `REQ-001` | `IMP-004` | `INV-001` | A second render for the same tenant within 3,600 seconds is a cache hit; a render at or after expiry recomputes and refreshes the entry. | Verify using a controllable clock rather than a real-time wait. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-002` | Role-change invalidation evicts the affected tenant's dashboard cache entry before the next response is served. | Add an integration or unit test covering permission invalidation followed by dashboard render. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-003` | Handling dashboard.updated evicts the affected tenant's cached response before the next render. | Add a test that seeds the cache, processes the update event, and observes a miss. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| api/dashboard.py cache storage, tenant-scoped lookup, and 3,600-second expiry | api/dashboard.py is the render owner named by the request. | verified |
| Role-change cache coherence | cache/permission_cache.py declares role-change invalidation and dashboard.response linkage. | inferred; the fixture exposes metadata but no callable invalidation API yet. |
| dashboard.updated cache coherence | events/dashboard_updated.py declares the event and dashboard.response linkage. | inferred; the fixture exposes metadata but no subscriber API yet. |
| Graph paths for IMP-001 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Graph paths for IMP-002 | PATH-002: cache/permission_cache.py → dashboard.response | PATH-002: provider builtin; confidence lexical; location cache/permission_cache.py + events/dashboard_updated.py |
| Graph paths for IMP-003 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Graph paths for IMP-004 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 40690bfa59a70789e309748b76abd1be; sha256 62a7bb32bd0e55e074e91309d3f456a9c8efe2de03ed44efc182c4bf0fb30967; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Ready for implementation. Preserve tenant isolation and response shape; add callable invalidation hooks where the current metadata-only modules do not yet expose them, then verify TTL, tenant partitioning, role-change invalidation, and dashboard.updated invalidation. |
