# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | One-hour caching of the rendered dashboard value | A cache key that omits tenant_id can serve a response carrying the wrong tenant identifier. | Dashboard consumers and tenant data isolation | Requests for different tenants share a cached full response. | high | Either key the full response by tenant_id or cache only tenant-neutral body data and rebuild the tenant envelope for every call. | refining |
| `IMP-002` | A 3,600-second dashboard cache lifetime | Entries may live longer or shorter than intended, refresh on access unexpectedly, or lack deterministic expiration. | Dashboard freshness and repeated-request behavior | A request occurs at or near the one-hour boundary. | high | Define fixed 3,600-second expiry from cache insertion using an injectable or controllable clock, and test before, at, and after expiry. | refining |
| `IMP-003` | Reuse of cached dashboard data | A caller can mutate a shared cached dictionary and corrupt later responses. | All in-process callers of render_dashboard | The cache stores and returns the same mutable dictionary object. | medium | Cache an immutable tenant-neutral value or return a fresh copy/envelope on every call. | refining |
| `IMP-004` | Stateful reuse of dashboard results for one hour | Concurrent misses can duplicate work, and process-local caches can disagree across workers or grow without bounds. | Runtime workers, memory use, and cache consistency | Simultaneous requests, multiple worker processes, or many tenant keys | medium | Select an explicit local or shared backend, define atomic fill/locking expectations and bounded eviction, and document accepted multi-worker behavior. | refining |
| `IMP-005` | A new runtime cache dependency or in-memory cache | Backend failures may break the dashboard, and cache effectiveness or expiry failures may be invisible. | Dashboard availability and operators | Cache read/write errors, unavailable shared infrastructure, or ineffective caching | medium | Specify fail-open behavior to recompute the current response, plus minimal hit/miss/error observability appropriate to the selected backend. | refining |
| `IMP-006` | One-hour cache behavior around render_dashboard | Incorrect keying, expiration, object reuse, or fallback can ship without detection. | Dashboard correctness across tenants and over time | The cache implementation changes without executable boundary tests. | high | Add deterministic tests for same/different tenants, cache hits, the 3,600-second boundary, independent returned objects, concurrent misses as applicable, and cache failure fallback. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Brainstorming approved a design to cache dashboard.response for one hour; refine repository impacts next from api/dashboard.py and render_dashboard. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Cache the dashboard result associated with dashboard.response for 3,600 seconds while preserving render_dashboard(tenant_id)'s exact tenant-specific two-key response and preventing cached state from leaking or being mutated across tenants or calls. The requirement is not ready for writing-plans until the cache boundary/backend is selected, because the repository contains no route, cache infrastructure, runtime topology, dependency configuration, or test convention that resolves those semantics. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | render_dashboard(tenant_id) returns exactly a dictionary whose tenant value is the supplied tenant_id and whose body value is the string dashboard.response. | verified | api/dashboard.py:1 and api/dashboard.py:3-4 directly define RESPONSE and the returned two-key dictionary. |
| `INV-002` | Each result identifies the tenant supplied for that call; one tenant's identifier must not be returned for another tenant. | verified | api/dashboard.py:4 assigns the current tenant_id directly to the returned tenant field. |
| `INV-003` | Each call currently constructs a new dictionary and exposes no shared mutable application state. | verified | api/dashboard.py:4 contains a dictionary literal inside render_dashboard, and api/dashboard.py:1-4 contains no mutation, imports, I/O, or cache state. |
| `INV-004` | The current repository has no demonstrated cache backend, configuration, dependency manifest, route integration, worker topology, or automated test harness. | verified | The repository source inventory contains only api/dashboard.py; repository-wide inspection found no other application, configuration, dependency, or test files. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-005`, `IMP-006` | api/dashboard.py:1 and api/dashboard.py:3-4 directly define RESPONSE and the returned two-key dictionary. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-006` | api/dashboard.py:4 assigns the current tenant_id directly to the returned tenant field. |
| `INV-003` | `REQ-001` | `IMP-003`, `IMP-004`, `IMP-006` | api/dashboard.py:4 contains a dictionary literal inside render_dashboard, and api/dashboard.py:1-4 contains no mutation, imports, I/O, or cache state. |
| `INV-004` | `REQ-001` | `IMP-002`, `IMP-004`, `IMP-005`, `IMP-006` | The repository source inventory contains only api/dashboard.py; repository-wide inspection found no other application, configuration, dependency, or test files. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | high | refining | unknown | api/dashboard.py:4 makes the full returned value tenant-specific, so caching the full dictionary under a global key could return one tenant identifier to another tenant. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | functionality | high | refining | unknown | The approved evidence specifies one hour, but api/dashboard.py:1-4 has no clock, expiry, refresh, or invalidation behavior and no repository file defines those semantics. | `INV-001`, `INV-004` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | compatibility | medium | refining | unknown | api/dashboard.py:4 currently creates a new mutable dictionary on every call; returning the same cached dictionary instance would change that observable behavior and allow mutation to bleed into later calls. | `INV-001`, `INV-003` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | state/concurrency | medium | refining | unknown | Caching introduces the repository's first demonstrated application state, while no lock, worker model, shared backend, eviction rule, or duplicate-fill behavior exists in the inspected repository. | `INV-003`, `INV-004` | the pending decision | `AC-004` |
| `IMP-005` | `REQ-001` | operations | medium | refining | unknown | The repository has no cache dependency, configuration, logging, metrics, backend failure policy, or deployment settings. | `INV-001`, `INV-004` | the pending decision | `AC-005` |
| `IMP-006` | `REQ-001` | regression | high | refining | unknown | No test file, test runner configuration, or project dependency manifest exists, so tenant isolation, TTL expiry, mutation isolation, concurrency, and failure fallback are unprotected. | `INV-001`, `INV-002`, `INV-003`, `INV-004` | the pending decision | `AC-006` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which cache boundary and backend should the approved one-hour dashboard cache use? | Cache the full rendered dictionary in process memory, keyed by tenant_id, for 3,600 seconds, returning a fresh copy per call. | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | Smallest repository change and no external dependency, but each worker has an independent cache and memory/eviction plus duplicate-fill behavior must be bounded. |
| Which cache boundary and backend should the approved one-hour dashboard cache use? | Cache the full rendered dictionary in a shared backend, keyed by tenant_id, for 3,600 seconds, returning a deserialized fresh value per call. | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | Consistent across workers and deployments, but requires backend selection, dependencies, configuration, serialization, failure handling, and operational ownership absent from this repository. |
| Which cache boundary and backend should the approved one-hour dashboard cache use? | Cache only the tenant-neutral RESPONSE body for 3,600 seconds and construct a fresh tenant dictionary on every call. | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | Preserves tenant isolation and fresh-object behavior with one global entry, but the current body is already a module constant, so this adds state with no demonstrated performance benefit and may not satisfy the intended full-response cache. |

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
| `REQ-001` | Cache the dashboard result associated with dashboard.response for 3,600 seconds while preserving render_dashboard(tenant_id)'s exact tenant-specific two-key response and preventing cached state from leaking or being mutated across tenants or calls. The requirement is not ready for writing-plans until the cache boundary/backend is selected, because the repository contains no route, cache infrastructure, runtime topology, dependency configuration, or test convention that resolves those semantics. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | Calls for two distinct tenant_id values must always return their respective tenant fields during hits, misses, and expiry refresh. | Future acceptance target derived from api/dashboard.py:4; no current cache exists. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-001` | A cached value is reused before 3,600 seconds from insertion and recomputed at or after the defined expiry boundary under a controllable clock. | Future acceptance target derived from the approved one-hour design; current code supplies no TTL behavior. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | Mutating one returned dictionary must not alter any later returned dictionary or cached value. | Future acceptance target preserving the new dictionary created by api/dashboard.py:4 on every current call. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-004` | The selected backend documents and tests the accepted same-process and multi-worker behavior, bounds entries or eviction, and defines duplicate-fill handling. | Future acceptance target required because no runtime topology, cache backend, or concurrency mechanism exists in the repository. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-001` | A cache read or write failure must fail open by producing the same response shape and values as the current uncached function, with observable error handling. | Future acceptance target preserving api/dashboard.py:3-4 when new cache operations fail. |
| `AC-006` | `REQ-001` | `IMP-006` | `INV-004` | Automated tests cover tenant isolation, hit/miss behavior, the one-hour expiry boundary, mutation isolation, selected concurrency semantics, and backend failure fallback. | Future acceptance target; repository inspection found no existing test harness or test files. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Direct implementation surface | api/dashboard.py:1-4 is the only application source and defines both RESPONSE and render_dashboard. | Verified for this repository inventory. |
| Callers, route registration, serializers, and downstream consumers | Repository-wide inspection found none; the promoted graph receipt returned no paths. | Unknown beyond this repository because FRONTIER-001 records unavailable ast-grep, codegraph, and scip providers. |
| Cache backend, configuration, dependencies, deployment topology, and operational ownership | No corresponding files or declarations exist in the repository. | Verified absent from the repository; external infrastructure remains unknown. |
| Automated regression coverage | No tests or test runner configuration exist in the repository. | Verified absent from the repository; external test systems remain unknown. |
| Graph paths for IMP-001 | The promoted graph receipt contains no paths and preserves FRONTIER-001 because ast-grep, codegraph, and scip providers were unavailable; this impact is bounded to direct inspection of the supplied render_dashboard location and cannot establish external callers. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-002 | No receipt-local graph path was returned; the provider-unavailable frontier prevents verification of route- or backend-level expiration behavior outside the supplied file. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-003 | The scan returned no caller paths, so whether consumers mutate the dictionary is unknown; the risk is based only on the verified current construction behavior. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-004 | The provider-unavailable frontier leaves runtime topology and transitive concurrency paths unverified; no repository evidence identifies whether deployments are single-process or multi-worker. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-005 | No graph path connects render_dashboard to an operational integration, and the provider-unavailable frontier means an external owner cannot be identified from repository evidence. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-006 | The graph receipt has no test paths and preserves the provider-unavailable frontier; absence is verified only for the supplied repository inventory, not for external test systems. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 1 nodes / 0 edges · 1 unknown frontiers | provider_limited; receipt e4833bdfabba335520151b70b72eabd4; sha256 226bae62510fd47d7c7578df8e1b92b6b778a99be95a2ae38bee2c5da01a945b; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006` | superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans |
