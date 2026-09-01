# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | One-hour caching of the dashboard response | A shared full-response cache can reuse the first tenant's payload for other tenants. | Any consumer calling render_dashboard for more than one tenant | The complete returned mapping is cached under a static dashboard.response key. | high | Select a tenant-independent cache unit or include tenant_id in every full-response cache key. | blocked |
| `IMP-002` | Reuse of a cached dashboard value | Callers may observe mutations made through a previously returned cached dict. | All callers sharing a cached entry | render_dashboard returns the cached mutable mapping by reference. | high | Cache only immutable body data or return a newly constructed/copy-isolated mapping on every call. | blocked |
| `IMP-003` | A 3,600-second dashboard cache lifetime | Entries can expire too early, remain stale beyond one hour, or be refreshed inconsistently. | Dashboard users around the expiration boundary | TTL measurement and expiration behavior are left implicit. | medium | Define a 3,600-second TTL using an injectable monotonic clock and test hits immediately before and recomputation at or after expiry. | refining |
| `IMP-004` | Storage and lifecycle of one-hour cached entries | Per-process caches can diverge or grow without bounds, while a shared backend can introduce configuration and availability failures. | Runtime instances and dashboard availability | A backend is chosen without defining process scope, eviction, bounds, and failure behavior. | medium | Select the backend scope explicitly and require bounded storage plus a defined cache-failure fallback. | blocked |
| `IMP-005` | Caching behavior in render_dashboard | Cross-tenant reuse, shared mutation, or incorrect expiry can ship undetected. | All dashboard callers | The cache is implemented without a new deterministic test harness. | medium | The planning owner must select a Python test framework and add deterministic tenant, mutation, hit, expiry, and failure tests before implementation is accepted. | deferred |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Brainstorming approved a design to cache dashboard.response for one hour; refine repository impacts next from api/dashboard.py and render_dashboard. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Implement the approved one-hour cache for dashboard.response at render_dashboard, while preserving the current tenant-specific payload and fresh-result behavior. The requirement is not ready for planning until the cache unit, tenant keying, and backend scope are selected; the implementation must use a 3,600-second TTL, prevent cross-tenant reuse, avoid sharing a caller-mutable cached dict, and define verifiable hit, expiry, and failure behavior. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | render_dashboard(tenant_id) returns a mapping whose tenant value is the supplied tenant_id. | verified | api/dashboard.py:3-4 directly returns {"tenant": tenant_id, "body": RESPONSE}. |
| `INV-002` | The dashboard body remains the value dashboard.response. | verified | api/dashboard.py:1 defines RESPONSE as dashboard.response and api/dashboard.py:4 places RESPONSE in the body field. |
| `INV-003` | Each current render_dashboard call creates a new result mapping, so mutation of one returned mapping does not alter a later result. | verified | api/dashboard.py:4 contains a dict literal in the return statement and no retained module or object state. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-004`, `IMP-005` | api/dashboard.py:3-4 directly returns {"tenant": tenant_id, "body": RESPONSE}. |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005` | api/dashboard.py:1 defines RESPONSE as dashboard.response and api/dashboard.py:4 places RESPONSE in the body field. |
| `INV-003` | `REQ-001` | `IMP-002`, `IMP-005` | api/dashboard.py:4 contains a dict literal in the return statement and no retained module or object state. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | high | blocked | unknown | Direct inspection shows tenant_id is embedded in the returned mapping, but the approved design and repository do not define a cache key or cache unit. A single cached full response under dashboard.response could return one tenant's tenant value to another tenant. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | state/concurrency | high | blocked | unknown | The current function creates a fresh mutable dict per call. Caching and returning that same dict instance would let one caller's mutation alter later results. | `INV-003`, `INV-001`, `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | functionality | medium | refining | unknown | The approved design supplies a one-hour duration, but api/dashboard.py has no clock, TTL, invalidation, refresh, or boundary convention. | `INV-002` | the pending decision | `AC-003`, `AC-004` |
| `IMP-004` | `REQ-001` | operations | medium | blocked | unknown | The complete repository inventory contains only api/dashboard.py; there is no dependency manifest, application configuration, cache utility, process lifecycle, or failure-handling convention. | `INV-001`, `INV-002` | the pending decision | `AC-005` |
| `IMP-005` | `REQ-001` | regression | medium | deferred | unknown | No tests, fixtures, test configuration, or dependency manifest exist in the repository, so current behavior and time-based cache behavior have no automated regression coverage. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-001`, `AC-002`, `AC-004`, `AC-005` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which cache unit and runtime scope should the one-hour dashboard cache use? | Cache only the tenant-independent body and build a fresh tenant envelope on every call. | `IMP-001`, `IMP-002`, `IMP-004` | Safest tenant and mutation semantics with the least repository change, but caching the current constant body provides little performance benefit and remains process-local unless a shared backend is later introduced. |
| Which cache unit and runtime scope should the one-hour dashboard cache use? | Cache the complete response per tenant in an in-process bounded TTL cache. | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Can avoid repeated per-tenant rendering without external infrastructure, but every process has independent entries and the implementation must copy results, bound memory, and key by tenant. |
| Which cache unit and runtime scope should the one-hour dashboard cache use? | Cache the complete response per tenant in a shared cache backend. | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Provides cross-process reuse and consistent TTL scope, but requires a new dependency/configuration contract plus serialization, availability, and fallback handling absent from this repository. |

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
| `REQ-001` | Implement the approved one-hour cache for dashboard.response at render_dashboard, while preserving the current tenant-specific payload and fresh-result behavior. The requirement is not ready for planning until the cache unit, tenant keying, and backend scope are selected; the implementation must use a 3,600-second TTL, prevent cross-tenant reuse, avoid sharing a caller-mutable cached dict, and define verifiable hit, expiry, and failure behavior. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Calls for different tenant_id values never reuse a full response across tenants, and each returned tenant field equals the call argument. | Required target derived from api/dashboard.py:3-4 and the missing cache-key contract. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | Mutating a mapping returned by one call cannot alter any later render_dashboard result, whether the later call is a cache hit or miss. | Required target preserving the current new-dict-per-call behavior at api/dashboard.py:4. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-002` | A cached value is eligible for reuse for less than 3,600 seconds and is recomputed at or after the 3,600-second expiry boundary. | The approved design states one hour; no repository TTL semantics currently exist. |
| `AC-004` | `REQ-001` | `IMP-003` | `INV-002` | Deterministic tests prove a hit within the TTL and recomputation at expiry without wall-clock sleeping. | Time behavior is new and the repository has no existing test or clock abstraction. |
| `AC-005` | `REQ-001` | `IMP-004` | `INV-002` | The selected cache has bounded storage and a documented failure path that preserves a valid dashboard response when cache access is unavailable. | No backend, bounds, lifecycle, or cache-error behavior is present in the repository. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | Cache unit and keying are unspecified; a static full-response key would violate the tenant invariant. | none | Approved-design owner |
| `IMP-002` | blocked | The cache strategy must determine whether immutable body data or complete mappings are retained and how callers receive isolated results. | none | Approved-design owner |
| `IMP-004` | blocked | The repository supplies no backend or runtime-scope convention; the selected option determines dependencies, configuration, and failure handling. | none | Approved-design owner |
| `IMP-005` | deferred | There is no test framework in the repository; the planning owner must select one and cover the refined criteria. | none | Planning owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Direct implementation surface: api/dashboard.py:1-4, especially render_dashboard. | This is the only source file and the only location containing dashboard.response or render_dashboard. | High for direct behavior. |
| Callers, authorization boundaries, and downstream mutation behavior. | No callers or other source files are present, and the graph receipt has no paths with a provider-unavailable frontier. | Unknown; must remain an explicit frontier. |
| Cache dependencies, runtime topology, configuration, and test infrastructure. | No manifest, lockfile, configuration, cache utility, tests, or fixtures are present. | High that the repository supplies no convention; low confidence about the intended external environment. |
| Graph paths for IMP-001 | The graph receipt returned no paths and an explicit provider-unavailable frontier, so transitive callers and authorization boundaries cannot be verified; this row is bounded to supplied evidence and direct source inspection. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-002 | The graph receipt contains no caller paths and reports provider unavailability, so downstream mutation behavior is unknown; the risk follows from the direct return type and proposed retained cache state. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-003 | No graph path supports cache lifecycle behavior and the receipt exposes a provider-unavailable frontier; the repository contains no additional source, configuration, or tests. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-004 | The graph receipt has no dependency paths and explicitly reports provider unavailability, so deployment topology and runtime consumers remain outside verified coverage. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-005 | The graph receipt contains no test paths and the complete visible inventory has only api/dashboard.py; test framework ownership cannot be established. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 1 nodes / 0 edges · 1 unknown frontiers | provider_limited; receipt c59ab1189e32a27585d1c0eae320ece9; sha256 223b0a8c802cb6ef32e9169f0c4c5d16dbd5bd3d33fdef70afb1afc0e3f79589; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005` | `IMP-001`, `IMP-002`, `IMP-004`, `IMP-005` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005` | superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans |
