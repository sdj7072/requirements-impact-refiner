# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Caching the complete render_dashboard result | A cache entry reused across tenant IDs could return the wrong tenant envelope and create a cross-tenant data boundary failure. | All callers of render_dashboard and any tenant-scoped dashboard consumer. | Two distinct tenant_id values resolve to the same cache entry. | critical | If the full response is cached, include a canonical tenant_id in the cache key and test alternating and concurrent tenants; otherwise cache only the shared body. | refining |
| `IMP-002` | One-hour reuse of the dashboard response | Entries may live for the wrong duration, never expire, or refresh at an unintended boundary. | Dashboard callers relying on the approved one-hour freshness window. | A request occurs before, at, or after 3,600 seconds from cache population. | high | Define the TTL as exactly 3,600 seconds from successful population and verify reuse before expiry plus refresh after expiry with a controllable clock. | refining |
| `IMP-003` | Selection of the value stored in the one-hour cache | Planning the wrong cache unit could either fail to cache the intended work or accidentally cache tenant-specific state as shared state. | render_dashboard's implementation, cache keys, and tests. | Implementation begins without deciding whether dashboard.response means the full returned mapping or only RESPONSE/body. | high | Choose one of the mutually exclusive cache units before writing-plans and keep the existing function signature and return shape. | refining |
| `IMP-004` | Concurrent population and refresh of cache entries | Simultaneous misses or expiry may perform duplicate population, expose partial state, or cache failures depending on the selected backend. | Concurrent dashboard requests for the same cache key. | Two or more callers miss or refresh the same entry at once. | medium | Require atomic publication of only successful complete values; document whether duplicate computation is acceptable and test same-key concurrency against the chosen cache mechanism. | detected |
| `IMP-005` | Runtime ownership of the one-hour cache | A process-local cache may provide inconsistent hit rates across workers, grow without bounds by tenant, or retain entries across an unintended lifecycle. | Deployment workers, memory usage, observability, and cache reset behavior. | The service runs multiple workers, receives many distinct tenant IDs, restarts, or needs emergency invalidation. | medium | Writing-plans must identify the existing cache/backend convention or explicitly bound a process-local cache, define startup/restart behavior, and add hit/miss/expiry observability appropriate to the repository. | detected |
| `IMP-006` | Cached behavior replacing unconditional response construction | Contract, tenant isolation, TTL boundary, and concurrency regressions could ship undetected. | render_dashboard consumers and future cache maintenance. | The cache implementation changes return values or timing behavior without focused automated checks. | high | Add tests for unchanged response shape, distinct tenants, hit reuse, 3,600-second expiry, failed population, and concurrent same-key access using deterministic time and isolated cache state. | detected |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Brainstorming approved a design to cache dashboard.response for one hour; refine repository impacts next from api/dashboard.py and render_dashboard. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Not ready for writing-plans: preserve render_dashboard(tenant_id)'s current response contract while adding an exact 3,600-second cache only after choosing whether the cache stores the complete tenant-specific response or only the shared dashboard body. Any complete-response cache must be isolated by tenant_id, must not return one tenant's envelope for another tenant, and must have explicit expiry, population-concurrency, lifecycle, and regression-test behavior. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | For every call, the returned mapping's tenant field equals the tenant_id argument supplied to that call. | verified | api/dashboard.py:3-4 constructs and returns {"tenant": tenant_id, "body": RESPONSE}. |
| `INV-002` | The returned mapping contains body equal to the module-level RESPONSE value "dashboard.response". | verified | api/dashboard.py:1 and api/dashboard.py:4 define RESPONSE and place it in the returned body field. |
| `INV-003` | render_dashboard remains a synchronous one-argument function returning a mapping directly. | verified | api/dashboard.py:3-4 defines a synchronous function accepting tenant_id and immediately returning a dict. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003`, `IMP-006` | api/dashboard.py:3-4 constructs and returns {"tenant": tenant_id, "body": RESPONSE}. |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-003`, `IMP-006` | api/dashboard.py:1 and api/dashboard.py:4 define RESPONSE and place it in the returned body field. |
| `INV-003` | `REQ-001` | `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | api/dashboard.py:3-4 defines a synchronous function accepting tenant_id and immediately returning a dict. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | refining | unknown | The source verifies that tenant_id is embedded in the returned object, but the repository contains no cache implementation or call-site evidence establishing cache key isolation. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | functionality | high | refining | unknown | The approved requirement supplies a one-hour duration, but api/dashboard.py has no cache, clock, expiry, refresh, or invalidation behavior. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | interfaces | high | refining | unknown | The request names dashboard.response, while the repository exposes both a RESPONSE body constant and a complete tenant-bearing return value; the approved cache unit is therefore not distinguishable from available evidence. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | state/concurrency | medium | detected | unknown | No cache population, locking, atomic insert, or error behavior exists in the only repository source file. | `INV-003` | the pending decision | `AC-004` |
| `IMP-005` | `REQ-001` | operations | medium | detected | unknown | The repository has no dependency manifest, configuration, service lifecycle, cache metrics, or invalidation facility. | `INV-003` | the pending decision | `AC-005` |
| `IMP-006` | `REQ-001` | regression | high | detected | unknown | No tests or test configuration are present in the repository inventory; only api/dashboard.py and refiner artifacts exist. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-006` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What exactly should the approved one-hour dashboard cache store? | Cache each complete render_dashboard result under a tenant-scoped key. | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | Caches the full response as users likely experience it, but requires canonical tenant keys, bounded entry lifecycle, concurrency semantics, and strict cross-tenant tests. |
| What exactly should the approved one-hour dashboard cache store? | Cache only the shared RESPONSE/body value and construct the tenant envelope on every call. | `IMP-002`, `IMP-003`, `IMP-005`, `IMP-006` | Avoids storing tenant-specific response objects and preserves tenant isolation by construction, but the current body is a constant so the cache adds complexity with negligible work saved. |

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
| `REQ-001` | Not ready for writing-plans: preserve render_dashboard(tenant_id)'s current response contract while adding an exact 3,600-second cache only after choosing whether the cache stores the complete tenant-specific response or only the shared dashboard body. Any complete-response cache must be isolated by tenant_id, must not return one tenant's envelope for another tenant, and must have explicit expiry, population-concurrency, lifecycle, and regression-test behavior. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Calls for two different tenant_id values, including alternating and concurrent calls, always return their respective tenant values and never reuse the other tenant's complete cached response. | Required to preserve the verified tenant echo behavior under any full-response cache. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | A successfully populated entry is reusable for less than 3,600 seconds and is treated as expired at the defined 3,600-second boundary; an expired request publishes a new successful value. | The approved design specifies one hour; deterministic boundary behavior is absent from current code. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | render_dashboard remains synchronous, accepts tenant_id, and returns exactly the existing tenant/body mapping regardless of cache hit or miss. | api/dashboard.py:3-4 verifies the current public shape. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-003` | Concurrent same-key misses publish only complete successful values, never cache an exception or partial value, and have an explicitly tested duplicate-computation policy. | No current cache or concurrency contract exists, so the implementation must make publication behavior explicit. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-003` | The selected cache owner, maximum key growth or eviction bound, worker-sharing behavior, restart behavior, invalidation mechanism, and hit/miss/expiry visibility are documented or tied to verified repository conventions. | No dependency, configuration, lifecycle, or observability evidence exists in the current repository. |
| `AC-006` | `REQ-001` | `IMP-006` | `INV-002` | Automated tests isolate cache state and cover miss, hit, exact expiry boundary, distinct tenants, failed population, and concurrent same-key access while asserting the unchanged response mapping. | No tests are present in the current repository inventory. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| api/dashboard.py:1-4 and render_dashboard | This is the only application source file present and directly defines RESPONSE plus the tenant-bearing return value. | High for the local function contract; low for transitive consumers because the graph receipt contains no paths. |
| Cache backend, configuration, runtime topology, and lifecycle | No dependency manifest, configuration, cache implementation, or deployment files are present. | Unknown; writing-plans must not assume a backend or single-worker runtime. |
| Call sites and authorization boundaries | The promoted scan contains no graph paths and reports provider fallback. | Unknown; no repository evidence establishes caller count, tenant validation, or external interface ownership. |
| Automated tests | No test files or test configuration are present in the current repository inventory. | High for this workspace inventory, unknown for external validation. |
| Graph paths for IMP-001 | The promoted graph receipt contains no paths and reports provider fallback; direct source inspection identifies the tenant-bearing response, but transitive cache consumers and authorization boundaries remain unknown. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-002 | The one-hour duration is supplied evidence and the graph receipt has no verified paths to a cache provider or clock abstraction. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-003 | This ambiguity comes from supplied wording plus direct source shape; the graph receipt provides no call or data-flow path that resolves which value consumers regard as dashboard.response. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-004 | The graph receipt has no concurrency or cache-provider paths, so runtime topology and concurrent callers are unknown. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-005 | Only api/dashboard.py is present and the graph provider yielded no operational paths, so process topology and deploy-time cache ownership cannot be verified. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-006 | The graph receipt has no test paths; absence was verified only within the current repository inventory and cannot establish external test coverage. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 1 nodes / 0 edges · 1 unknown frontiers | provider_limited; receipt 8cb62585c430c0ad6a14229217531a58; sha256 7f453e2b211de16e9d9d09e944236d0cad89e2c8f78371347dec7de1312c8f93; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006` | superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans |
