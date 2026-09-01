# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | A one-hour cache is introduced for dashboard responses. | If the cache is global or keyed incompletely, one tenant can receive a response labeled or populated for another tenant. | All callers rendering dashboards for more than one tenant, with a potential cross-tenant privacy breach. | Two different tenant_id values access the cache during the same entry lifetime. | high | Key every entry by the complete tenant identity and verify isolation with alternating-tenant and concurrent-tenant tests. | detected |
| `IMP-002` | A rendered dashboard response may be reused for one hour. | Entries can outlive the intended 3,600-second bound or refresh inconsistently if TTL start, expiry, and clock behavior are unspecified. | Dashboard users who expect updates to appear after the approved cache window. | A request arrives at or after an entry's expiration boundary, or the runtime clock changes. | medium | Define TTL from successful insertion using a monotonic clock where applicable, treat age &gt;= 3,600 seconds as expired, and cover the exact boundary with a controllable clock. | detected |
| `IMP-003` | The renderer's result is retained and reused instead of reconstructed on every call. | A caller mutation can contaminate subsequent responses if the same cached dictionary instance is returned. | Later dashboard requests for the same tenant and any code that assumes an independent return value. | A caller mutates a returned dictionary before another cache hit. | high | Cache an immutable representation or return a fresh copy on every hit and miss; add a mutation-isolation regression test. | detected |
| `IMP-004` | render_dashboard gains time-based shared state. | Workers can serve inconsistent cache generations, duplicate expensive refreshes, or block/fail requests differently depending on cache topology. | Concurrent dashboard requests and multi-worker deployments. | Concurrent misses, expiration, worker restart, or cache-backend failure. | high | Choose per-process or shared caching explicitly, then define miss coalescing, atomic publication, and fail-open rendering behavior appropriate to that choice. | blocked |
| `IMP-005` | The source of render_dashboard's return value changes from immediate construction to cached retrieval. | Caching can alter the return shape, tenant labeling, object independence, or error timing observed by callers. | Every direct or indirect consumer of render_dashboard. | A cache hit, miss, expiration, or backend error follows a different return path. | medium | Keep the public signature and mapping contents unchanged and run the same contract assertions through hit, miss, expiry, and failure paths. | detected |
| `IMP-006` | Dashboard rendering begins depending on cache state and expiration. | Cache failures or pathological misses can become request failures or remain invisible in production. | Operators and users during cache outage, restart, or elevated miss rates. | The selected cache cannot be read or written, entries churn, or workers restart. | medium | Render on cache failure, avoid caching failed results, and expose hit, miss, expiry, refresh, and error signals compatible with the selected topology. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Brainstorming approved a design to cache dashboard.response for one hour; refine repository impacts next from api/dashboard.py and render_dashboard. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Not ready for planning: preserve render_dashboard's tenant-specific response contract while caching each tenant's dashboard response for no more than 3,600 seconds, without exposing a cached mutable object to callers. The cache topology and its corresponding miss/failure behavior must be selected before writing-plans. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | render_dashboard(tenant_id) returns a mapping with exactly the current tenant and body fields, and body remains dashboard.response. | verified | api/dashboard.py:1-4 defines RESPONSE as dashboard.response and returns {'tenant': tenant_id, 'body': RESPONSE}. |
| `INV-002` | The tenant value in each returned dashboard response corresponds to the tenant_id supplied for that call. | verified | api/dashboard.py:3-4 copies tenant_id directly into the returned tenant field. |
| `INV-003` | Each current render_dashboard call constructs a new dictionary, so mutation of one returned value does not affect a later call. | verified | api/dashboard.py:4 contains a dictionary literal in the function return expression. |
| `INV-004` | The current renderer has no cache, clock, I/O, or shared mutable state and returns directly from its input and module constant. | verified | The complete api/dashboard.py file is four lines; render_dashboard only returns the tenant_id and RESPONSE values. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-002`, `IMP-003`, `IMP-005` | api/dashboard.py:1-4 defines RESPONSE as dashboard.response and returns {'tenant': tenant_id, 'body': RESPONSE}. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-004`, `IMP-005` | api/dashboard.py:3-4 copies tenant_id directly into the returned tenant field. |
| `INV-003` | `REQ-001` | `IMP-003` | api/dashboard.py:4 contains a dictionary literal in the function return expression. |
| `INV-004` | `REQ-001` | `IMP-002`, `IMP-004`, `IMP-006` | The complete api/dashboard.py file is four lines; render_dashboard only returns the tenant_id and RESPONSE values. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | high | detected | unknown | Direct source inspection shows tenant_id is part of the response, but the promoted graph receipt contains no path proving callers, cache-key construction, or tenancy boundaries. | `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | functionality | medium | detected | unknown | The approved design supplies a one-hour lifetime, while the repository contains no clock, expiration definition, refresh behavior, or downstream freshness requirements. | `INV-001`, `INV-004` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | regression | high | detected | unknown | api/dashboard.py currently returns a fresh mutable dictionary, but no receipt path identifies whether callers mutate it or whether the proposed cache stores that dictionary directly. | `INV-003`, `INV-001` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | state/concurrency | high | blocked | unknown | No cache backend, process model, caller graph, synchronization primitive, or deployment configuration exists in the repository evidence. | `INV-004`, `INV-002` | the pending decision | `AC-004` |
| `IMP-005` | `REQ-001` | interfaces | medium | detected | unknown | The direct function contract is visible in api/dashboard.py, but no callers, serialization layer, or tests are available to confirm all interface expectations. | `INV-001`, `INV-002` | the pending decision | `AC-005` |
| `IMP-006` | `REQ-001` | operations | medium | refining | unknown | The repository has no configuration, metrics, logging, invalidation hook, dependency manifest, or operational documentation for a cache. | `INV-004` | the pending decision | `AC-006` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which cache topology should writing-plans treat as the approved repository boundary? | Per-process, tenant-keyed in-memory cache | `IMP-004`, `IMP-006` | Adds no infrastructure and fits the current tiny repository, but each worker has independent entries and refresh timing; restarts cold-start the cache. |
| Which cache topology should writing-plans treat as the approved repository boundary? | Shared, tenant-keyed cache | `IMP-004`, `IMP-006` | Provides cross-worker reuse and more consistent generations, but adds a backend, serialization, network-failure behavior, configuration, and operational ownership. |

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
| `REQ-001` | Not ready for planning: preserve render_dashboard's tenant-specific response contract while caching each tenant's dashboard response for no more than 3,600 seconds, without exposing a cached mutable object to callers. The cache topology and its corresponding miss/failure behavior must be selected before writing-plans. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | For any tenant A and tenant B, cached calls return A only for A and B only for B, including alternating and concurrent calls. | Derived from the verified tenant_id-to-response relationship in api/dashboard.py:3-4. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-004` | A successfully cached value is reusable only while its age is less than 3,600 seconds; at age 3,600 seconds or greater, the next request refreshes it. | The one-hour lifetime is supplied by the approved design; the current source has no expiration behavior. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | Mutating one returned mapping never changes the result of a later render_dashboard call, whether the later call is a hit or miss. | Preserves the verified fresh-dictionary behavior of api/dashboard.py:4. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-004` | The implementation documents and tests the selected process scope, concurrent-miss behavior, atomic publication, restart behavior, and cache-failure fallback. | These semantics are newly required because no shared state exists in the current four-line module. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-001` | Miss, hit, expiration, and cache-failure paths all preserve render_dashboard(tenant_id) and return the current tenant/body mapping with body equal to dashboard.response. | Derived from the verified current signature and mapping at api/dashboard.py:1-4. |
| `AC-006` | `REQ-001` | `IMP-006` | `INV-004` | A cache read or write failure falls back to rendering the current response, does not cache an error, and emits an observable cache-error signal. | The current renderer has no external failure mode; the cache introduces one whose handling is not present in repository evidence. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-004` | blocked | Per-process and shared caching create materially different repository, dependency, concurrency, and operational impacts; the approved one-hour lifetime does not select between them. | none | Product/architecture owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| api/dashboard.py, RESPONSE, and render_dashboard | The workspace contains api/dashboard.py as its only non-refiner source file; lines 1-4 define the full visible dashboard behavior. | high for the local function contract |
| Callers, routing, serialization, authorization enforcement, and tests | No additional source or test files are present, and the promoted scan produced no receipt-local paths. | unknown |
| Runtime topology, cache backend, configuration, deployment, and observability | No dependency, configuration, deployment, or operations files are present in repository evidence. | unknown |
| Graph paths for IMP-001 | Supplied seed and direct file evidence only; the scan frontier reports that ast-grep, codegraph, and SCIP providers were unavailable, so transitive confidence is not upgraded. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-002 | No receipt-local paths were produced; freshness consumers remain on the provider-unavailable unknown frontier. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-003 | Direct source establishes the fresh-object baseline only; caller mutation behavior is unknown because the scan produced no transitive paths. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-004 | The only repository source is api/dashboard.py and the graph receipt has a provider-unavailable frontier with no paths; cache topology and concurrency semantics cannot be verified. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-005 | The scan found no transitive paths, so downstream compatibility remains unknown even though the local return shape is verified. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-006 | Operational surfaces are absent from supplied evidence and no graph path was produced; the provider-unavailable frontier prevents a stronger claim. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 1 nodes / 0 edges · 1 unknown frontiers | provider_limited; receipt 7017f9ea661abb3059f52025cb2b0c97; sha256 db27f7fd50d10e7f75172295b9395276f61430e69f9e2af753985ea7784f9a08; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | `IMP-004` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006` | superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans |
