# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | One-hour caching of the dashboard response unit | A global cache of the full returned mapping can return one tenant's identifier for another tenant and cross the tenant isolation boundary. | Callers of render_dashboard and any tenant whose identifier is included in a cached result | Two different tenant_id values use the same cache entry within the 3,600-second lifetime | high | Choose an explicit cache unit: key the full result by tenant_id, or cache only tenant-independent body data and reconstruct the tenant field per call. | blocked |
| `IMP-002` | Reuse of cached dashboard data | Returning the same cached dictionary lets one caller's mutation affect later callers and creates shared-state races. | All callers receiving a cache hit | A caller mutates a dictionary that is stored and returned directly from the cache | high | Cache immutable data or return a new mapping/defensive copy for every call, including cache hits. | detected |
| `IMP-003` | A 3,600-second cache lifetime | Entries may live too long, expire inconsistently, or be refreshed from wall-clock jumps if TTL semantics are implicit. | All dashboard responses served after their first computation | Time crosses the intended one-hour boundary or an implementation uses a non-monotonic/incorrect expiry calculation | medium | Define TTL as 3,600 seconds from insertion, ensure expired entries are recomputed before return, and test just-before/at/after expiry with a controllable clock. | refining |
| `IMP-004` | Cache integration around render_dashboard | Callers can break if caching changes the function signature, sync behavior, or returned mapping shape. | Any direct or imported caller of render_dashboard | The cache implementation adds required arguments, returns an awaitable, or changes tenant/body fields | medium | Keep the existing signature and synchronous mapping contract; inject testable cache/clock dependencies without making them required public arguments. | detected |
| `IMP-005` | Shared one-hour dashboard cache | Concurrent misses can cause duplicate work, inconsistent publication, or tenant-key collisions. | Concurrent callers for the same or different tenant keys | Multiple calls observe an absent or expired entry simultaneously | medium | Use atomic cache publication and tenant-safe keys; at minimum guarantee all concurrent results satisfy current output and mutation-isolation invariants. | detected |
| `IMP-006` | Regression coverage for dashboard caching | A cache can appear correct on a single hit while failing tenant isolation, exact expiry, mutation isolation, or concurrent access. | Maintainers and all dashboard callers | The implementation is planned or shipped without deterministic cache-state and clock-controlled tests | medium | Add focused tests for miss/hit, different tenants, fresh returned mappings, expiry boundaries, and concurrent misses using a resettable cache and controllable clock. | detected |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Brainstorming approved a design to cache dashboard.response for one hour; refine repository impacts next from api/dashboard.py and render_dashboard. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Not ready for writing-plans until the cache unit and tenant-keying decision is made. After that decision, render_dashboard(tenant_id) must cache the approved dashboard response unit for 3,600 seconds while preserving the current synchronous one-argument interface, returning the requested tenant_id and body value "dashboard.response", and avoiding shared mutable result state across calls. The implementation scope currently evidenced is api/dashboard.py; cache backend, callers, configuration, invalidation hooks, and tests are not present in the visible repository. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | render_dashboard(tenant_id) returns a mapping whose tenant field equals the supplied tenant_id. | verified | api/dashboard.py:3-4 directly constructs {"tenant": tenant_id, "body": RESPONSE}. |
| `INV-002` | The returned body field is the string "dashboard.response". | verified | api/dashboard.py:1 assigns RESPONSE = "dashboard.response" and line 4 returns RESPONSE as body. |
| `INV-003` | render_dashboard remains a synchronous function accepting exactly one tenant_id argument. | verified | api/dashboard.py:3 defines def render_dashboard(tenant_id). |
| `INV-004` | Each invocation currently constructs a new result mapping, so one caller cannot mutate another caller's returned mapping. | verified | api/dashboard.py:4 contains a dictionary literal inside render_dashboard, which creates a new mapping on each call. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | api/dashboard.py:3-4 directly constructs {"tenant": tenant_id, "body": RESPONSE}. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-003`, `IMP-004`, `IMP-006` | api/dashboard.py:1 assigns RESPONSE = "dashboard.response" and line 4 returns RESPONSE as body. |
| `INV-003` | `REQ-001` | `IMP-004`, `IMP-006` | api/dashboard.py:3 defines def render_dashboard(tenant_id). |
| `INV-004` | `REQ-001` | `IMP-002`, `IMP-005`, `IMP-006` | api/dashboard.py:4 contains a dictionary literal inside render_dashboard, which creates a new mapping on each call. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | high | blocked | unknown | The visible result contains tenant_id, while "dashboard.response" appears only as a string assigned to RESPONSE. The approved wording does not establish whether the full tenant-bearing mapping or only its tenant-independent body is cached. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | state/concurrency | high | detected | unknown | render_dashboard currently returns a newly constructed mutable dictionary on every invocation. Caching and returning that dictionary instance would change object-identity and mutation-isolation behavior. | `INV-004` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | functionality | medium | refining | unknown | The approved design supplies a one-hour duration, but the visible repository has no cache implementation, clock source, expiry convention, or invalidation behavior. | `INV-001`, `INV-002` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | compatibility | medium | detected | unknown | The only evidenced public surface is synchronous render_dashboard(tenant_id). Introducing a backend parameter, async behavior, or a wrapper-only cache would alter this surface. | `INV-003`, `INV-001`, `INV-002` | the pending decision | `AC-004` |
| `IMP-005` | `REQ-001` | state/concurrency | medium | detected | unknown | No cache primitive or deployment topology is visible. Concurrent misses could compute multiple values or publish partially shared mutable state depending on the chosen implementation. | `INV-004`, `INV-001` | the pending decision | `AC-005` |
| `IMP-006` | `REQ-001` | regression | medium | detected | unknown | The visible repository contains api/dashboard.py only; no tests, dependency manifest, cache abstraction, or test clock are present. | `INV-001`, `INV-002`, `INV-003`, `INV-004` | the pending decision | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What exactly should the one-hour cache store, given that render_dashboard returns tenant-specific data but "dashboard.response" is only the constant body string? | Cache the full response per tenant_id and return a fresh mapping from the cached immutable value. | `IMP-001`, `IMP-002`, `IMP-005` | Preserves tenant isolation and enables full-result reuse, but creates one cache entry per tenant and requires tenant-safe key normalization. |
| What exactly should the one-hour cache store, given that render_dashboard returns tenant-specific data but "dashboard.response" is only the constant body string? | Cache only the tenant-independent body value globally for one hour and reconstruct {tenant, body} on every call. | `IMP-001`, `IMP-002`, `IMP-003` | Uses one entry and naturally preserves per-call tenant/mapping behavior, but may provide little benefit because the currently evidenced body computation is only a constant lookup. |
| What exactly should the one-hour cache store, given that render_dashboard returns tenant-specific data but "dashboard.response" is only the constant body string? | Cache and return the full mutable mapping directly. | `IMP-001`, `IMP-002`, `IMP-005` | Is mechanically smallest but is unsafe without per-tenant keys and changes the current fresh-object behavior; it should be selected only if shared mutation is explicitly acceptable. |

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
| new | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Not ready for writing-plans until the cache unit and tenant-keying decision is made. After that decision, render_dashboard(tenant_id) must cache the approved dashboard response unit for 3,600 seconds while preserving the current synchronous one-argument interface, returning the requested tenant_id and body value "dashboard.response", and avoiding shared mutable result state across calls. The implementation scope currently evidenced is api/dashboard.py; cache backend, callers, configuration, invalidation hooks, and tests are not present in the visible repository. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | For any sequence of calls using tenant IDs A and B, every returned tenant field equals that call's argument; no cache entry can expose A in B's result. | Required to preserve api/dashboard.py:4 across cache hits and mixed-tenant calls. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-004` | Mutating a mapping returned by one invocation does not change the result of any later invocation, including a cache hit. | Matches the current per-invocation dictionary construction at api/dashboard.py:4. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-002` | A cached value is reusable for less than 3,600 seconds from insertion; at the 3,600-second boundary it is treated as expired and recomputed before being returned. | Makes the approved one-hour duration testable without relying on sleeps. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-003` | Existing calls to synchronous render_dashboard(tenant_id) continue to return a mapping with exactly the evidenced tenant and body fields without requiring new arguments. | Preserves api/dashboard.py:3-4. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-001` | Concurrent calls for the same and different tenant IDs never publish a result under the wrong key and all returned mappings satisfy tenant and mutation-isolation criteria. | Covers the shared-state behavior introduced by caching while preserving api/dashboard.py:4. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The approved duration does not identify the cached unit or cache key boundary, and the two viable units have materially different behavior and value. | none | Product/design owner who approved the dashboard cache, with implementation owner confirming tenant-key semantics |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Direct implementation surface: api/dashboard.py and render_dashboard. | The visible repository contains only api/dashboard.py; lines 1-4 define RESPONSE and render_dashboard. | high for the direct file; unknown for external or omitted callers |
| Behavior to preserve: synchronous signature, tenant echo, body value, and per-call mapping isolation. | All four behaviors are directly visible in api/dashboard.py:1-4. | high |
| Transitive callers, cache backend, deployment topology, invalidation sources, configuration, and test framework. | No corresponding files or receipt paths are present; the promoted scan retained a provider-unavailable frontier. | unknown |
| Graph paths for IMP-001 | The promoted receipt contains no impact paths and retains a provider-unavailable frontier, so transitive tenant consumers cannot be verified; this row remains unknown despite direct source inspection. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-002 | No receipt-local caller path exists, so whether callers mutate the returned mapping is unknown and cannot be promoted beyond the supplied/direct boundary. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-003 | The receipt has no cache/configuration path and retains a provider frontier, so expiry and invalidation integrations remain unknown. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-004 | No caller path was present in the promoted receipt, so compatibility with external or unindexed callers remains unknown. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-005 | The promoted receipt contains no runtime or cache-backend path, so process/thread sharing and atomicity are unknown. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-006 | The receipt has no test or configuration paths and a provider-unavailable frontier, so hidden or external verification surfaces cannot be established. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 1 nodes / 0 edges · 1 unknown frontiers | provider_limited; receipt 0d80c40e8bdd80c90a8d1a932c7ca747; sha256 34d41893b802d3dceab0c4d5c5d0cf166dfad777c9cce913e7bd0e18e6c955cf; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | `IMP-001` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005` | superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans |
