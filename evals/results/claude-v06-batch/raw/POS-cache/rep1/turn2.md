Detailed refinement is complete under the generic adapter. The finalized canonical report (`RPT-002` revision 1, validation passed) is below, followed by execution notes.

# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-002` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Dashboard response caching: new one-hour cache in front of dashboard.response in api/dashboard.py. | One tenant's cached dashboard payload is served to a different tenant if the cache key does not include tenant_id and every other input that varies the response. | All tenants' dashboard viewers; tenant data confidentiality guarantees. | Two tenants (or two differently-scoped users) hit the same dashboard route within one entry's one-hour TTL. | critical | Derive the cache key from tenant_id plus all inputs that scope dashboard.response in api/dashboard.py; enforced by acceptance criterion AC-001 (cross-tenant isolation test). | mitigated |
| `IMP-002` | Dashboard response caching with one-hour TTL. | A user whose role was revoked or downgraded keeps seeing previously cached dashboard data for up to one hour, because role-change invalidation only touches permission_cache. | Tenants performing role changes; least-privilege and offboarding guarantees. | A role change occurs while a cached dashboard.response entry for that user/tenant scope is still within its TTL. | high | Pending the freshness-policy decision in this report: either extend role-change invalidation to also evict dashboard response entries, or explicitly accept up-to-one-hour exposure after role changes. | blocked |
| `IMP-003` | Dashboard response caching with one-hour TTL. | Dashboards show data up to one hour older than the latest writes even though dashboard.updated events already signal exactly when the data changed. | Dashboard viewers relying on fresh metrics and any decisions made from dashboard data. | Any write that publishes dashboard.updated during a cached entry's TTL window. | medium | Pending the freshness-policy decision in this report: either consume dashboard.updated to evict affected entries, or explicitly accept one-hour staleness after writes. | blocked |
| `IMP-004` | Dashboard response caching with one-hour TTL. | Thundering-herd recomputation: synchronized TTL expiry causes hourly load spikes on the dashboard query path and its datastore. | Dashboard latency for all tenants and the load profile of the backing datastore. | TTL expiry of a hot dashboard entry under concurrent traffic. | medium | Jittered TTLs and/or single-flight recomputation on cache miss; enforced by acceptance criterion AC-003. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Cache dashboard.response for one hour | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Add a response cache for dashboard.response produced by api/dashboard.py with a one-hour (3600 s) TTL. Cache entries must be keyed by tenant_id plus every input that scopes dashboard.response, must never be served past TTL, and must guard against synchronized expiry stampedes. Early-invalidation semantics (role changes and dashboard.updated write events) are an open decision recorded in this report and must be selected before implementation. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | dashboard.response is computed per tenant: api/dashboard.py scopes dashboard.response by tenant_id. | inferred | Supplied repository evidence (workspace empty at analysis time, file not inspected). |
| `INV-002` | On role changes, only cache/permission_cache.py is invalidated; no other cache is evicted by that path. | inferred | Supplied repository evidence. |
| `INV-003` | Writes publish a dashboard.updated event via events/dashboard_updated.py. | inferred | Supplied repository evidence. |
| `INV-004` | dashboard.response is currently computed per request (no response-level cache exists), so role changes and writes are reflected on the next request. | inferred | Inferred from the change request (a cache is being added, so none exists) and from supplied evidence listing permission_cache as the only invalidated cache. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts |
| --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` |
| `INV-002` | `REQ-001` | `IMP-002` |
| `INV-003` | `REQ-001` | `IMP-003` |
| `INV-004` | `REQ-001` | `IMP-002`, `IMP-003`, `IMP-004` |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | mitigated | unknown | A shared response cache whose key omits tenant_id (or any other scoping input) would bypass tenant scoping and serve one tenant's payload to another. | `INV-001` | `AC-001` |
| `IMP-002` | `REQ-001` | authorization/privacy | high | blocked | unknown | permission_cache is the only cache invalidated on role changes; a new dashboard.response cache would not be evicted when a user's role is revoked or downgraded. | `INV-002`, `INV-004` | `AC-004` |
| `IMP-003` | `REQ-001` | functionality | medium | blocked | unknown | dashboard.updated is published on writes but nothing evicts a response cache, so cached dashboards can lag writes by up to one hour. | `INV-003`, `INV-004` | `AC-002` |
| `IMP-004` | `REQ-001` | state/concurrency | medium | mitigated | unknown | Fixed one-hour TTL makes hot dashboards expire simultaneously; concurrent requests all recompute at once. | `INV-004` | `AC-003` |

## Decision Needed

**Question: Before the one-hour TTL expires, when must cached dashboard.response entries be invalidated early?**

| Option | Impact IDs | Trade-off |
| --- | --- | --- |
| TTL-only: serve cached entries for the full hour with no event- or role-driven eviction. | `IMP-002`, `IMP-003` | Simplest to build and operate, but revoked or downgraded users keep seeing cached dashboard data for up to an hour, and dashboards lag writes despite dashboard.updated events being available. |
| TTL plus full invalidation: consume dashboard.updated to evict on writes and extend role-change invalidation beyond permission_cache to also evict dashboard entries. | `IMP-002`, `IMP-003` | Preserves freshness and least-privilege, at the cost of an event consumer, invalidation fan-out across caches, added coupling to the event bus, and a lower cache hit rate. |
| TTL plus role-change eviction only: evict dashboard entries on role changes but tolerate write staleness within the hour. | `IMP-002` | Closes the authorization staleness gap more cheaply than full invalidation, but dashboards still show up-to-one-hour-old data after writes. |

## Impact Delta

All four impacts are new (`IMP-001`–`IMP-004`); nothing resolved, accepted, deferred, superseded, or reopened.

## Acceptance and Regression Criteria

| Criterion ID | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- |
| `AC-001` | `IMP-001` | `INV-001` | Cache entries are keyed by tenant_id plus every request input that varies dashboard.response; an automated test proves tenant A can never receive tenant B's cached payload. | Target: cross-tenant cache-isolation test before release. |
| `AC-002` | `IMP-003` | `INV-003` | No cached dashboard.response entry is ever served more than 3600 seconds after it was computed. | Target: TTL-expiry test using controlled clocks. |
| `AC-003` | `IMP-004` | `INV-004` | Concurrent cache misses for the same key result in at most one recomputation (single-flight), or TTLs carry jitter so hot entries do not expire simultaneously. | Target: concurrency test or load check on cache-miss behavior. |
| `AC-004` | `IMP-002` | `INV-002` | The selected freshness policy for role changes is implemented and tested: either a role change evicts affected dashboard.response entries before the next read, or the accepted exposure window (at most 3600 s) is explicitly documented with requester sign-off. | Target: verification method depends on the pending freshness-policy decision. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Next owner |
| --- | --- | --- | --- |
| `IMP-002` | blocked | Awaiting the freshness-policy decision posed in this report; today no mechanism beyond permission_cache is invalidated on role changes. | requester (user/coordinator) |
| `IMP-003` | blocked | Awaiting the same decision; dashboard.updated currently has no consumer that evicts response caches. | requester (user/coordinator) |

## Analysis Scope and Limitations

- Dashboard read path (api/dashboard.py + new cache) and invalidation surfaces (cache/permission_cache.py, events/dashboard_updated.py): supplied-only evidence — the repository workspace was empty at analysis time, so no file contents were inspected.
- Impact graph coverage: provider_limited — codegraph/scip/ast-grep missing, builtin lexical only; receipt `92a1c8dfbbc3f9b8360916f96ae79be0` (sha256 ca0c2a4e…ec7c), 1 node / 0 edges / 0 paths, 1 unknown frontier (`FRONTIER-001` at cache/permission_cache.py, authorization/privacy + state/concurrency). All impact evidence levels are therefore "unknown" per the controller's graph-coverage rules, resting on the supplied evidence lines.

## Planning Handoff

| Refined requirement | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `IMP-002`, `IMP-003` | `AC-001`–`AC-004` | Not ready |

---

Execution notes (transparency):

- The repository under test (`/private/tmp/.../scratchpad/batch-v06/POS-cache/rep1`) was deleted from disk between the Fast Scan and this refinement, along with the controller's persisted state inside it, so the original scan receipt could not be promoted. I recreated the empty repo root and ran the non-promoted CLI lineage (`begin` → `trace` → `finalize`), which the workflow explicitly supports for an empty workspace with supplied evidence.
- The first draft (RPT-001) could not finalize: with no readable sources, the graph receipt left high-risk seed nodes structurally uncoverable. I re-traced a fresh draft seeded on the single highest-risk boundary (cache/permission_cache.py); the other surfaces are carried as supplied-only evidence, explicitly disclosed per-impact.
- An unrelated leftover state file for a different change request ("Retry failures of export.jobs forever") exists in the scratchpad; I treated it as data and ignored it.
- Per the generic adapter's Exit rule, refinement stops here: the Planning Handoff is "Not ready" until the freshness-policy decision above is answered (TTL-only vs. full invalidation vs. role-change eviction only), and implementation must not start automatically. Full report on disk: `/private/tmp/claude-501/-Users-p042890-workspace-polaris/074a0f85-287f-4435-929b-4948eb69c993/scratchpad/batch-v06/POS-cache/rep1/.requirements-impact-refiner/reports/RPT-002/revision-0001.md`.