# Requirements impact report: permanent shared links

## Requirement revision

`REQ-001`: Make shared links permanent.

The request establishes the desired change; the meaning of “permanent” across permission changes and signing-key rotation remains the pending decision.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Level | Evidence | Links |
| --- | --- | --- | --- | --- |
| `INV-001` | Share tokens expire after seven days. | `verified` | User-supplied repository fact: “share tokens currently expire after seven days.” | `must-preserve` `REQ-001` as the baseline to be explicitly revised |
| `INV-002` | Permission changes revoke active share tokens. | `verified` | User-supplied repository fact: “permission changes revoke active tokens.” | `must-preserve` `REQ-001` unless the pending decision changes this policy |
| `INV-003` | Token-signing keys rotate every 90 days. | `verified` | User-supplied repository fact: “token signing keys rotate every 90 days.” | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | Removing the seven-day expiry changes the token validity contract and requires a precise definition of permanence. | `verified` | `INV-001`; supplied seven-day expiry fact | `refining` | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | If permission changes continue to revoke tokens, a link can stop working despite having no time-based expiry; if they do not, access can persist after authorization changes. | `verified` | `INV-002`; supplied permission-revocation fact | `refining` | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | A 90-day signing-key rotation may invalidate existing tokens unless the permanence policy defines how already-issued tokens are handled across rotation. | `verified` | `INV-003`; supplied key-rotation fact | `refining` | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | Indefinite link validity increases the exposure window for a leaked or mis-shared link, so revocation and access-control expectations must be explicit. | `inferred` | Consequence of `REQ-001` combined with `INV-001`–`INV-003`; no repository security policy was supplied | `detected` | `affects` `REQ-001`; `produces` `AC-004` |

## One focused decision

What should “permanent” mean when permissions change or signing keys rotate?

1. **Permanent but revocable (recommended):** remove time-based expiry; preserve revocation when permissions change; keep existing links valid across signing-key rotation; provide/retain an explicit revocation path.
2. **Permanent within current security boundaries:** remove time-based expiry; preserve permission-change revocation; allow signing-key rotation to invalidate older tokens.
3. **Persistent until explicit revocation:** remove time-based expiry and automatic permission-change revocation; keep links valid across key rotation; access ends only through explicit link revocation.

Decision status: the pending decision; no decision ID is recorded.

## Whole-set recalculation (before the decision)

No policy has been selected, so the complete known impact set remains open. Existing `detected` and `refining` impacts are unchanged pending the decision.

### Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`
- `accepted`: none
- `deferred`: none
- `blocked`: none
- `new`: none

## Stop check and planning handoff

Impact refinement cannot close yet: `IMP-001`–`IMP-004` require the pending policy choice. After selection, recalculate the full set and produce acceptance criteria:

- `AC-001`: Shared links follow the selected permanence definition rather than expiring after seven days.
- `AC-002`: Permission-change behavior matches the selected revocation policy.
- `AC-003`: Existing links follow the selected behavior across 90-day signing-key rotation.
- `AC-004`: The resulting indefinite-access and explicit-revocation behavior is testable and documented.

Planning handoff is pending the single decision above; no implementation plan or repository modification is proposed in this report.
--- USER REVISION ---
Make links non-expiring, but preserve revocation on permission changes and key rotation. I explicitly accept exposure until an explicit revoke event. Recalculate every impact. Continue the same evaluation. Do not write implementation tasks or modify the repository. Recalculate the entire known impact set, preserve accepted versus resolved semantics, and produce the report-only planning handoff. Preserve the existing .part1 byte-for-byte. Assemble the final transcript at .superpowers/sdd/2026-08-20-requirements-impact-refiner/task7-compat-rerun1/codex-standalone/POS-sharing.md by writing the exact .part1 content, then a `--- USER REVISION ---` separator, then the exact user revision above, then the complete second response. The second response delta must be pairwise disjoint and exhaustive and show resolved, mitigated, unchanged, accepted, deferred, blocked, and new using none where needed. Return only DONE plus the path.

# Requirements impact report: revised non-expiring links

## Requirement revision

`REQ-002`: Shared links are non-expiring; permission changes and signing-key rotation revoke active links; exposure remains accepted until an explicit revoke event.

`REQ-002` refines `REQ-001` through `DEC-001`.

## Current behavior and preserved invariants

| ID | Behavior / invariant after the explicit revision | Level | Evidence | Links |
| --- | --- | --- | --- | --- |
| `INV-001` | The prior seven-day expiry is superseded by the non-expiring requirement. | `verified` | Prior supplied fact and explicit user revision | `must-preserve` `REQ-002` as the superseded baseline being revised |
| `INV-002` | Permission changes revoke active share tokens. | `verified` | Supplied permission-revocation fact; explicit user revision | `must-preserve` `REQ-002` |
| `INV-003` | Signing-key rotation revokes active links. | `verified` | Supplied 90-day key-rotation fact; explicit user revision | `must-preserve` `REQ-002` |

## Recorded decision

`DEC-001`: “Make links non-expiring, but preserve revocation on permission changes and key rotation. I explicitly accept exposure until an explicit revoke event.”

This decision refines `REQ-002`, resolves the permanence semantics, and accepts the indefinite-exposure risk in `IMP-004`.

## Recalculated impact ledger

| ID | Impact | Level | Evidence | State | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The seven-day expiry no longer applies because the revised requirement explicitly makes links non-expiring. | `verified` | `DEC-001`; supplied seven-day expiry fact | `resolved` | `affects` `REQ-002`, `INV-001`; `mitigated by` `DEC-001`; `produces` `AC-001` |
| `IMP-002` | Permission-change revocation is explicitly preserved, so authorization changes continue to invalidate active links. | `verified` | `DEC-001`; supplied permission-revocation fact | `resolved` | `affects` `REQ-002`, `INV-002`; `mitigated by` `DEC-001`; `produces` `AC-002` |
| `IMP-003` | Signing-key rotation is explicitly a revocation event for active links, so existing links do not remain valid across rotation. | `verified` | `DEC-001`; supplied 90-day key-rotation fact | `resolved` | `affects` `REQ-002`, `INV-003`; `mitigated by` `DEC-001`; `produces` `AC-003` |
| `IMP-004` | Indefinite validity leaves exposure from a leaked or mis-shared link until an explicit revoke event; the user explicitly accepts that risk. | `inferred` | `DEC-001`; consequence identified from the supplied token lifecycle facts | `accepted` | `affects` `REQ-002`; `accepted by` `DEC-001`; `produces` `AC-004` |

## Delta

- `resolved`: `IMP-001`, `IMP-002`, `IMP-003`
- `mitigated`: none
- `unchanged`: none
- `accepted`: `IMP-004`
- `deferred`: none
- `blocked`: none
- `new`: none

The categories are pairwise disjoint and exhaustive over the known impact set: `IMP-001` through `IMP-004` each appears exactly once.

## Stop check and report-only planning handoff

Impact refinement is complete. The remaining risk is the accepted indefinite exposure represented by `IMP-004`; it is not marked resolved because acceptance does not eliminate the risk.

Acceptance criteria:

- `AC-001`: A shared link remains valid beyond seven days unless revoked by a defined revocation event.
- `AC-002`: A permission change revokes the affected active shared link.
- `AC-003`: Signing-key rotation revokes active shared links.
- `AC-004`: The system documents and tests that a non-expiring link remains exposed until an explicit revoke event, and records that this exposure is accepted.

This is a report-only planning handoff for `REQ-002`, linked to `DEC-001`; no implementation tasks or repository modifications are included.
