# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Cache render_dashboard results for one hour. | A global cache entry can leak or mislabel tenant-specific responses. | Any caller rendering dashboards for more than one tenant. | A cache hit occurs for a tenant different from the tenant that populated the entry. | high | Key every full-response cache entry by tenant_id and test interleaved tenants. | refining |
| `IMP-002` | Reuse cached dashboard results. | One caller can mutate a cached dictionary and corrupt later responses, including during concurrent use. | All callers sharing the same tenant cache entry. | A caller mutates a returned dictionary before another cache hit. | high | Cache immutable payload data or return a fresh copy on every hit, with a mutation-isolation test. | refining |
| `IMP-003` | Expire dashboard cache entries after one hour. | Entries may expire early, remain stale past one hour, or behave nondeterministically at the boundary. | Callers expecting the approved one-hour freshness window. | Time reaches or crosses the entry's expiry timestamp, or the system wall clock changes. | medium | Define 3600 seconds precisely, use a monotonic/injectable clock for local expiry, and test just-before, at, and after expiry. | refining |
| `IMP-004` | Store tenant-scoped cached dashboard responses. | A process-local cache behaves independently per worker, while a shared backend adds availability and configuration behavior not present in the repository. | Deployments with multiple processes or hosts and operators responsible for cache health. | The service runs in more than one process/host or the selected cache backend is unavailable. | high | Choose process-local or shared topology explicitly before planning and document its consistency and failure semantics. | blocked |
| `IMP-005` | Retain one cache entry per active tenant for up to one hour. | High tenant cardinality or stale entries can cause unbounded memory or backend growth. | Service processes or the selected shared cache backend. | Many distinct tenant IDs render dashboards within or across expiry windows. | medium | Define capacity and eviction/expired-entry cleanup appropriate to the selected topology and verify expired entries are reclaimable. | refining |
| `IMP-006` | Introduce stateful, time-dependent behavior into render_dashboard. | Unknown callers may depend on fresh objects or deployment-specific behavior, and cache regressions may go undetected. | Unseen route/controller consumers and the eventual test suite. | Implementation begins without the missing application/test context or equivalent acceptance tests. | high | Locate or supply the integration repository and add deterministic tests for hits, tenant isolation, mutation isolation, expiry, and selected-backend failure behavior. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Brainstorming approved a design to cache dashboard.response for one hour; refine repository impacts next from api/dashboard.py and render_dashboard. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Add a one-hour (3600-second) cache at render_dashboard in api/dashboard.py for the dashboard response while preserving the existing return contract: each result contains the requested tenant_id and body "dashboard.response", cache entries are isolated by tenant_id, callers cannot mutate cached state through a returned dictionary, and expiry behavior is deterministic and testable. Cache topology remains a required decision because the repository contains no runtime, deployment, dependency, or caller evidence. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | render_dashboard(tenant_id) returns a mapping whose tenant value equals that invocation's tenant_id. | verified | api/dashboard.py:3-4 accepts tenant_id and places it directly in the returned dictionary. |
| `INV-002` | The result remains a dictionary with tenant and body fields, and body remains the string dashboard.response. | verified | api/dashboard.py:1 and api/dashboard.py:4 define RESPONSE as dashboard.response and return it under body. |
| `INV-003` | Separate invocations do not expose shared mutable outer-dictionary state to callers. | verified | api/dashboard.py:4 constructs a new dictionary on every current invocation; the only shared value is an immutable string. |
| `INV-004` | A cached value is reusable for no more than 3600 seconds under the selected expiry boundary, after which render_dashboard recomputes or recreates it. | unknown | The approved design supplies a one-hour requirement, but the repository has no clock, cache, or expiry implementation to verify boundary semantics. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-004`, `IMP-005`, `IMP-006` | api/dashboard.py:3-4 accepts tenant_id and places it directly in the returned dictionary. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-006` | api/dashboard.py:1 and api/dashboard.py:4 define RESPONSE as dashboard.response and return it under body. |
| `INV-003` | `REQ-001` | `IMP-002`, `IMP-006` | api/dashboard.py:4 constructs a new dictionary on every current invocation; the only shared value is an immutable string. |
| `INV-004` | `REQ-001` | `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | The approved design supplies a one-hour requirement, but the repository has no clock, cache, or expiry implementation to verify boundary semantics. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | high | refining | unknown | api/dashboard.py:4 shows tenant_id is response data, so a non-tenant-keyed cached full response could return one tenant identifier for another request. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | state/concurrency | high | refining | unknown | api/dashboard.py:4 currently returns a fresh mutable dictionary; returning the same cached dictionary would create shared mutable state that does not exist today. | `INV-003`, `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | functionality | medium | refining | unknown | No clock or caching utility exists in the repository; exact behavior at 3600 seconds and wall-clock adjustments is therefore unspecified. | `INV-004` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | operations | high | blocked | unknown | The repository has no application bootstrap, deployment model, dependency manifest, configuration, or shared-cache client, so process count and cross-worker consistency needs cannot be established. | `INV-004`, `INV-001` | the pending decision | `AC-004` |
| `IMP-005` | `REQ-001` | operations | medium | refining | unknown | tenant_id is unconstrained in api/dashboard.py:3 and the repository contains no cache capacity, eviction, or cleanup convention. | `INV-001`, `INV-004` | the pending decision | `AC-005` |
| `IMP-006` | `REQ-001` | regression | high | blocked | unknown | Repository inventory contains only api/dashboard.py; there are no callers, routes, tests, test configuration, dependency manifests, or time-mocking conventions. | `INV-001`, `INV-002`, `INV-003`, `INV-004` | the pending decision | `AC-006` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which cache topology should the one-hour tenant-scoped dashboard cache use? | Process-local per-tenant TTL cache | `IMP-004`, `IMP-005`, `IMP-002` | Adds no external dependency and fits the visible repository, but each worker has independent entries and expiry, duplicate recomputation, and per-process memory. |
| Which cache topology should the one-hour tenant-scoped dashboard cache use? | Shared per-tenant TTL cache backend | `IMP-004`, `IMP-005`, `IMP-001` | Provides cross-worker reuse and centrally enforced expiry, but requires a new backend, serialization, configuration, availability/failure semantics, and integration evidence absent from this repository. |

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
| `REQ-001` | Add a one-hour (3600-second) cache at render_dashboard in api/dashboard.py for the dashboard response while preserving the existing return contract: each result contains the requested tenant_id and body "dashboard.response", cache entries are isolated by tenant_id, callers cannot mutate cached state through a returned dictionary, and expiry behavior is deterministic and testable. Cache topology remains a required decision because the repository contains no runtime, deployment, dependency, or caller evidence. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Interleaved calls for different tenant IDs never reuse another tenant's full response; the cache identity includes tenant_id. | Required by api/dashboard.py:3-4 because tenant_id is embedded in the response. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | Mutating one returned dictionary cannot change any later result, whether the later call is a cache hit or concurrent call. | Preserves the fresh dictionary behavior currently implemented at api/dashboard.py:4. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-004` | A value is reusable before 3600 elapsed seconds and is not reused at or after the defined 3600-second boundary; tests control time deterministically. | Makes the approved one-hour duration executable despite no existing repository time convention. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-004` | The selected topology documents whether entries are shared across workers/hosts and defines behavior when cache storage is unavailable. | No deployment, configuration, or cache-backend evidence exists in the repository. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-001` | The cache has a defined capacity/eviction policy and expired tenant entries are reclaimable rather than accumulating indefinitely. | tenant_id is an unconstrained cache-key input in api/dashboard.py:3. |
| `AC-006` | `REQ-001` | `IMP-006` | `INV-002` | Automated tests cover miss, hit, response shape, tenant separation, mutation isolation, before/at/after expiry, test-state reset, and the chosen topology's failure mode. | No tests or test infrastructure are present in the repository. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-004` | blocked | Process/deployment topology and consistency expectations are absent, and choosing a cache backend changes dependencies and failure behavior. | none | Product/architecture owner |
| `IMP-006` | blocked | No callers, routes, runtime configuration, dependency metadata, or test suite are available to verify the integration boundary. | none | Repository owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Direct change surface: api/dashboard.py:1-4, especially render_dashboard. | This is the only application source file and the only definition of render_dashboard and dashboard.response. | verified |
| Downstream callers, HTTP routing, response serialization, and deployment process model. | Repository-wide search found no callers, imports, routes, manifests, or deployment files. | unknown outside the supplied repository |
| Tests, clock controls, cache libraries, configuration, invalidation hooks, and observability. | None are present in the repository; all would be new or must be supplied from another integration repository. | verified absent here; external context unknown |
| Graph paths for IMP-001 | The promoted Fast Scan receipt contained no graph paths because ast-grep, codegraph, and SCIP providers were unavailable; this impact is inferred from direct inspection of api/dashboard.py:3-4. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-002 | The scan receipt supplied no call paths; the compatibility risk is inferred from the directly observed fresh-dictionary behavior in api/dashboard.py:4. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-003 | The graph receipt had no paths; this impact is derived from the supplied one-hour requirement and absence of time/cache code in the only application source file. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-004 | The scan frontier identified an interface unknown and supplied no paths; repository inventory contains only api/dashboard.py, leaving runtime topology unverified. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-005 | No graph path was available; memory growth is inferred from the required per-tenant key and the lack of repository cache infrastructure. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-006 | The Fast Scan could not produce graph paths and direct repository search found no integration boundary or test suite, so downstream compatibility remains unknown. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 1 nodes / 0 edges · 1 unknown frontiers | provider_limited; receipt c2e05bf1c3278ecc59bf96341e13a2fa; sha256 279c0262c85647f73ecc80ac72d21e4a7367e0a9255196a7fb458c426cea0da8; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | `IMP-004`, `IMP-006` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006` | superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans |
