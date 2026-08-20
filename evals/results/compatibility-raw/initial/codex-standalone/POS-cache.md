# Requirements Impact Refinement — Dashboard response caching

## Requirement revision

`REQ-001`: Cache the dashboard response for one hour, with cache behavior scoped correctly to the tenant and compatible with permission changes and dashboard updates. The exact cache-key and invalidation policy remains pending.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence | Level | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Dashboard results depend on `tenant_id`; responses must not be shared across tenants. | Supplied fact: dashboard results depend on `tenant_id`. | `verified` | `must-preserve` `REQ-001` |
| `INV-002` | Role changes invalidate `permission_cache`. | Supplied fact: role changes invalidate `permission_cache` only. | `verified` | `must-preserve` `REQ-001` |
| `INV-003` | Dashboard writes publish `dashboard.updated`. | Supplied fact: dashboard writes publish `dashboard.updated`. | `verified` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | A one-hour response cache must include `tenant_id` in its key; omitting it could serve one tenant’s dashboard to another tenant. | `verified` | `detected` | Dashboard results depend on `tenant_id`. | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | Because role changes invalidate only `permission_cache`, a previously cached dashboard response could remain permission-stale for up to one hour unless the selected policy adds dashboard-cache invalidation or rechecks authorization on cache hits. | `verified` | `refining` | One-hour requested TTL plus the stated `permission_cache`-only invalidation behavior. | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | Dashboard writes publish `dashboard.updated`, but the supplied facts do not establish whether that event currently invalidates or refreshes dashboard response entries; otherwise writes may remain stale until TTL expiry. | `verified` | `refining` | Supplied dashboard-write event fact; cache-consumer behavior is not supplied. | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | The supplied facts do not establish whether responses vary by actor, role, or other dimensions beyond `tenant_id`; a tenant-only key could be unsafe if the response is personalized or permission-filtered. | `unknown` | `blocked` | Only `tenant_id` dependence is supplied; response-variance and authorization semantics are unavailable. | `affects` `REQ-001`; `produces` `AC-004` |

## One focused decision

What freshness and authorization policy should govern the one-hour tenant-scoped response cache?

1. **Tenant key with event-driven invalidation (recommended)** — key entries by `tenant_id`, retain the one-hour TTL, invalidate the tenant’s dashboard response cache on role changes as well as `dashboard.updated`, and define the role-change event path needed for that invalidation. This gives predictable permission and write freshness but expands the current “`permission_cache` only” invalidation behavior.
2. **Tenant key with authorization recheck** — key entries by `tenant_id` and retain the one-hour TTL, but re-evaluate the caller’s current permissions on every cache hit; use `dashboard.updated` to invalidate or refresh data entries where applicable. This limits permission leakage without requiring role changes to evict the response body, but the response must be safe to reuse across callers and the extra checks may reduce the cache benefit.
3. **Tenant key with TTL-only staleness** — key entries by `tenant_id`, retain the one-hour TTL, and allow role and dashboard changes to leave existing responses cached until expiry. This preserves the narrow current invalidation contract but explicitly accepts up to one hour of stale permissions and dashboard data.

Please select one option, or specify another policy including cache-key dimensions, role-change behavior, and the handling of `dashboard.updated`. No decision has been recorded; no implementation plan or repository edit is produced.

## Recorded decision

Decision needed — no `DEC-###` is recorded because no user/stakeholder option has been selected.

## Whole-set recalculation (before decision)

All supplied impacts have been checked against the requested one-hour cache. No impact is resolved, mitigated, accepted, deferred, or new before the freshness and authorization decision.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-004`
- `new`: none

## Stop check and planning handoff

Stopped at the single required cache freshness/authorization decision. The refined requirement, preserved invariants, evidence-backed impacts, and provisional acceptance criteria are ready for continuation after selection; no implementation tasks, plan, or repository edit is included.

### Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | A cached response is never served across tenants; the selected cache key includes every required tenant dimension. | Produced by `IMP-001`; exact cache implementation is not inspected. |
| `AC-002` | After a role change, dashboard responses follow the selected permission-freshness policy and do not expose data under stale authorization. | Produced by `IMP-002`; current dashboard-cache and authorization flow are not supplied. |
| `AC-003` | After a dashboard write, the selected handling of `dashboard.updated` yields the documented freshness behavior. | Produced by `IMP-003`; event subscriber behavior is not supplied. |
| `AC-004` | Any response variation beyond `tenant_id` is explicitly included in the key or handled by per-request authorization. | Produced by blocked `IMP-004`; response and role-variance contract is unavailable. |

--- USER REVISION ---

Keep the one-hour TTL, key by tenant and authorization context, and invalidate on both `dashboard.updated` and role changes. Defer any broader cache redesign.

# Second response — recalculation after `DEC-001`

## Requirement revision

`REQ-001` is refined to: Cache dashboard responses for one hour using a key composed of `tenant_id` and the applicable authorization context. Invalidate the relevant cached response entries on both `dashboard.updated` and role changes. Defer any broader cache redesign beyond this scoped policy.

## Recorded decision

`DEC-001`: The user selected a one-hour TTL with cache keys partitioned by tenant and authorization context, plus invalidation on both `dashboard.updated` and role changes. Broader cache redesign is explicitly deferred.

## Whole-set recalculation

| ID | Recalculated impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Tenant isolation is addressed by including `tenant_id` in the selected cache key, alongside authorization context. | `verified` | `mitigated` | Supplied tenant dependency plus explicit `DEC-001` key policy. | `affects` `REQ-001`, `INV-001`; `mitigated by` `DEC-001` |
| `IMP-002` | Role changes now invalidate relevant dashboard response entries, preventing the selected cache from retaining permission-stale responses for the full TTL. | `verified` | `resolved` | Supplied role-change behavior plus explicit `DEC-001` role-change invalidation. | `affects` `REQ-001`, `INV-002`; `resolved by` `DEC-001` |
| `IMP-003` | `dashboard.updated` is an explicit invalidation trigger, so dashboard writes do not have to wait for one-hour expiry before cached data is discarded. | `verified` | `resolved` | Supplied event fact plus explicit `DEC-001` event invalidation. | `affects` `REQ-001`, `INV-003`; `resolved by` `DEC-001` |
| `IMP-004` | Response variation tied to authorization is covered by the selected authorization-context key; any other unenumerated variation remains outside the scoped change and is deferred with the broader redesign. | `unknown` | `deferred` | User selected tenant-plus-authorization keying and explicitly deferred broader cache redesign; other response dimensions are not supplied. | `affects` `REQ-001`; `deferred by` `DEC-001`; `produces` `AC-004` |
| `IMP-005` | Partitioning entries by authorization context and supporting two invalidation paths increases cache cardinality and coordination requirements; the supplied facts do not quantify the operational impact. | `inferred` | `refining` | New consequence of the selected key and invalidation policy; capacity and observability data are not supplied. | `affects` `REQ-001`; `produces` `AC-005` |

## Delta

- `resolved`: `IMP-002`, `IMP-003`
- `mitigated`: `IMP-001`
- `unchanged`: none
- `accepted`: none
- `deferred`: `IMP-004`
- `blocked`: none
- `new`: `IMP-005`

The categories are disjoint and exhaustive across `IMP-001` through `IMP-005`.

## Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | A dashboard response is never served across tenants, and the cache key includes `tenant_id` plus the selected authorization context. | Produced by mitigated `IMP-001`; exact context encoding is not inspected. |
| `AC-002` | A role change invalidates the affected authorization-context dashboard entries, so stale permission results are not retained for the full one-hour TTL. | Produced by resolved `IMP-002`; role-event wiring and tests are not supplied. |
| `AC-003` | `dashboard.updated` invalidates the affected tenant/authorization-context entries after a dashboard write. | Produced by resolved `IMP-003`; event subscriber behavior is not supplied. |
| `AC-004` | Broader response-key dimensions and cache redesign are explicitly out of scope for this change and tracked for later evaluation. | Produced by deferred `IMP-004`; unenumerated response variation remains unspecified. |
| `AC-005` | Cache cardinality, invalidation coordination, and observable hit/miss behavior for the selected policy are measured or bounded. | Produced by new `IMP-005`; capacity and observability evidence are unavailable. |

## Stop check and planning handoff

The cache policy decision is recorded and every known impact has been recalculated. `IMP-002` and `IMP-003` are resolved, `IMP-001` is mitigated, `IMP-004` is deferred with the broader redesign, and `IMP-005` remains a validation target. No implementation tasks, work breakdown, plan, or repository edit is included.

