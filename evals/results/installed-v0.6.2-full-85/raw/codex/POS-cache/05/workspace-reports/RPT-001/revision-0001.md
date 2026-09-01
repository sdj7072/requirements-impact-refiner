# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | One-hour caching of dashboard.response | A shared cache key can return one tenant's response to another tenant. | All dashboard tenants and their data isolation. | Two tenants render dashboard.response while the same cache entry remains live. | critical | Include tenant_id in every cache key and test that tenants never share entries. | refining |
| `IMP-002` | Serving dashboard responses for up to one hour | A user may continue receiving data based on obsolete permissions after a role change. | Users whose roles or permissions change and tenants containing them. | A role changes before the cached dashboard response expires. | critical | Evict or version affected tenant/dashboard entries as part of the role-change invalidation path. | refining |
| `IMP-003` | One-hour dashboard response cache | Dashboard changes may remain invisible until TTL expiry. | Tenants whose dashboard content changes. | dashboard.updated is published while a cached response exists. | high | Consume the event and invalidate the affected tenant entry; define payload tenant identity and idempotent handling. | refining |
| `IMP-004` | Adding cached mutable state | Process-local entries can diverge across workers and ignore invalidations delivered elsewhere. | Multi-worker or multi-instance deployments. | More than one process serves the same tenant or receives different invalidation events. | high | Choose a shared cache/event strategy, or explicitly constrain and test a single-process local cache. | blocked |
| `IMP-005` | Caching render results | Concurrent misses may race, duplicate work, or mutate shared cached objects. | Concurrent requests for the same tenant. | Two requests miss the same tenant entry simultaneously or callers mutate a returned mapping. | medium | Use safe cache access and return immutable/copy-isolated values; cover concurrent or re-entrant access. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Cache dashboard.response from api/dashboard.py for one hour. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Cache api/dashboard.py render results for 3,600 seconds using a tenant-scoped cache key. Preserve tenant isolation, invalidate affected dashboard responses when authorization/role state changes and when dashboard.updated is published, and define cache sharing/concurrency behavior for the deployment runtime. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | A dashboard response for one tenant is never returned to another tenant. | verified | api/dashboard.py render(tenant_id) embeds tenant_id in every response. |
| `INV-002` | Role changes invalidate authorization-sensitive cached state associated with dashboard.response. | verified | cache/permission_cache.py declares INVALIDATED_ON_ROLE_CHANGE and links RESPONSE_REF to dashboard.response. |
| `INV-003` | A dashboard update is represented by dashboard.updated and must make affected rendered responses refreshable. | inferred | events/dashboard_updated.py declares dashboard.updated and links it to dashboard.response, but contains no executable publisher or consumer. |
| `INV-004` | render(tenant_id) continues to return a mapping containing the requested tenant and dashboard.response body. | verified | api/dashboard.py currently returns {'tenant': tenant_id, 'body': RESPONSE}. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-004` | api/dashboard.py render(tenant_id) embeds tenant_id in every response. |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-004` | cache/permission_cache.py declares INVALIDATED_ON_ROLE_CHANGE and links RESPONSE_REF to dashboard.response. |
| `INV-003` | `REQ-001` | `IMP-003`, `IMP-004` | events/dashboard_updated.py declares dashboard.updated and links it to dashboard.response, but contains no executable publisher or consumer. |
| `INV-004` | `REQ-001` | `IMP-005` | api/dashboard.py currently returns {'tenant': tenant_id, 'body': RESPONSE}. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | refining | unknown | The response varies by tenant_id while the requested cache is for dashboard.response; the receipt's built-in fallback suggests a permission-cache to dashboard path but provider verification is unavailable. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | authorization/privacy | critical | refining | unknown | cache/permission_cache.py declares role-change invalidation and references dashboard.response; the receipt suggests a path to api/dashboard.py but provider verification is unavailable and no executable hook exists. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | state/concurrency | high | refining | unknown | events/dashboard_updated.py declares dashboard.updated and RESPONSE_LINK dashboard.response; the receipt suggests a path from permission cache to this event module but provider verification is unavailable and no subscriber exists. | `INV-003` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | operations | high | blocked | unknown | The repository has no cache client/backend, deployment model, locking, or event transport implementation. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-004` |
| `IMP-005` | `REQ-001` | state/concurrency | medium | refining | unknown | No thread-safety or cache-fill convention exists; the receipt path is built-in fallback only. | `INV-004` | the pending decision | `AC-005` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which cache scope should own the one-hour dashboard entries and their invalidation? | Shared cache with tenant-scoped keys and event-driven invalidation | `IMP-004`, `IMP-002`, `IMP-003`, `IMP-001` | Correct across workers and instances, but requires a shared cache/client and event plumbing that this repository does not currently define. |
| Which cache scope should own the one-hour dashboard entries and their invalidation? | Process-local in-memory cache, explicitly limited to a single-process deployment | `IMP-004`, `IMP-005`, `IMP-002`, `IMP-003` | Can be implemented with the standard library now, but each worker has independent state and invalidation is only reliable within one process. |
| Which cache scope should own the one-hour dashboard entries and their invalidation? | Tenant generation/version keys backed by an existing shared store | `IMP-004`, `IMP-002`, `IMP-003` | Avoids broad eviction and tolerates retries, but needs a shared authoritative version store whose API is not present in the repository. |

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
| new | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Cache api/dashboard.py render results for 3,600 seconds using a tenant-scoped cache key. Preserve tenant isolation, invalidate affected dashboard responses when authorization/role state changes and when dashboard.updated is published, and define cache sharing/concurrency behavior for the deployment runtime. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Given cached responses for two tenant IDs, each render returns only the response produced for its own tenant and uses a distinct cache entry. | Directly verifies the tenant-scoped key required by api/dashboard.py behavior. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | After a role/permission change for an affected tenant or principal, the next dashboard render does not reuse the pre-change response. | Required by cache/permission_cache.py role-change invalidation declaration. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | After dashboard.updated identifies an affected tenant, the next render for that tenant refreshes while unrelated tenant entries remain cached. | Required by events/dashboard_updated.py linkage to dashboard.response. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-003` | The selected design documents and tests invalidation behavior for every serving process in the supported deployment model. | No deployment or cache-backend evidence exists, so this must be made explicit before implementation. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-004` | Concurrent requests cannot corrupt cached state, and modifying one returned response cannot change later responses. | Cached Python mappings would otherwise be shared mutable objects. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-004` | blocked | No cache backend or deployment topology exists in the repository; implementation semantics differ materially between shared and process-local designs. | none | Request owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| api/dashboard.py render path and tenant-specific response identity | Inspected api/dashboard.py. | high |
| role/permission change invalidation linkage | Inspected cache/permission_cache.py; declarations exist but executable hooks do not. | medium |
| dashboard.updated publication/consumption linkage | Inspected events/dashboard_updated.py; constants exist but publisher/consumer code does not. | medium |
| cache backend, event transport, process topology, and tests | Repository inventory contains no implementation or configuration for these concerns. | unknown |
| Graph paths for IMP-001 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Graph paths for IMP-002 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Graph paths for IMP-003 | PATH-002: cache/permission_cache.py → dashboard.response | PATH-002: provider builtin; confidence lexical; location cache/permission_cache.py + events/dashboard_updated.py |
| Graph paths for IMP-004 | Supplied repository evidence and inspected files establish the logical links but do not establish whether the service is single-process or multi-worker. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-005 | PATH-001: cache/permission_cache.py → dashboard.response | PATH-001: provider builtin; confidence lexical; location cache/permission_cache.py + api/dashboard.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 8e31069c5955d4fa9233d8d0cb940c12; sha256 b1a65d96bc511b5cdf252c87f47b2c019cb6ba6a2678eb53b5b705607a1d1a34; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005` | `IMP-004` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005` | Not ready |
