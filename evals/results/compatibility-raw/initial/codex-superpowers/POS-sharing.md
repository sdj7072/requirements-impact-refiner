# Requirements Impact Refinement — Permanent shared links

## Status

`NEEDS_DECISION` — the initial request was under-specified. The first response recorded no decision and stopped at one focused question.

## Initial requirement and evidence

`REQ-001`: Make shared links permanent, with the meaning of permanence (stable URL, non-expiring credential, or both) to be selected. Supplied invariants: share tokens expire after seven days (`INV-001`, verified); permission changes revoke active share tokens (`INV-002`, verified); signing keys rotate every 90 days (`INV-003`, verified).

Initial impacts: `IMP-001` (seven-day expiry conflicts with permanence, verified/refining); `IMP-002` (non-expiring bearer access must preserve permission-change revocation, verified/detected); `IMP-003` (90-day key rotation needs rollover/history semantics for non-expiring links, verified/blocked); and `IMP-004` (resource/account deletion, audience, and authorization lifecycle are unspecified, unknown/blocked). Initial acceptance targets were `AC-001` through `AC-004`. No `DEC-###` was recorded before the user revision.

### Initial focused decision

The pending policy question was what “permanent” should mean for the URL, credential lifetime, revocation, and key rotation:

1. **Permanent URL with renewable, revocable access (recommended)** — keep the share address indefinitely, but renew credentials under authorization checks; permission changes and explicit revocation invalidate access, and key rotation does not change the URL.
2. **Long-lived token with retained verification history** — make the bearer token non-expiring, retain key metadata across 90-day rotations, and maintain explicit revocation state.
3. **Non-expiring public bearer link** — remove the seven-day expiry and allow validity across key rotations, with explicit revocation ending access; deletion behavior would require a separate policy.

No option was selected in the initial response, so its pre-decision delta was: `resolved: none`; `mitigated: none`; `unchanged: IMP-001, IMP-002`; `accepted: none`; `deferred: none`; `blocked: IMP-003, IMP-004`; `new: none`. The initial response stopped at this single decision and included no implementation plan.

## USER REVISION

> Make links non-expiring, but preserve revocation on permission changes and key rotation. I explicitly accept exposure until an explicit revoke event. Recalculate every impact.

## Recorded decision

`DEC-001`: Shared links use non-expiring bearer tokens. Permission changes continue to revoke active tokens; revocation state remains effective across signing-key rotation, and rotation must not invalidate or resurrect a link. An explicit revoke event is authoritative to end access. The requester explicitly accepts exposure from a disclosed token until an explicit revoke event; this acceptance does not waive permission-change revocation or key-rotation compatibility.

## Revised requirement

`REQ-001` (revised): Shared-link bearer tokens have no time-based expiry and remain verifiable across each 90-day signing-key rotation. Permission changes and explicit revoke events invalidate access, with revocation records surviving key rotation. Access may remain exposed until the revoke event is emitted and processed. Deleted-resource/account behavior remains a separate lifecycle policy.

## Complete post-decision impact recalculation

| ID | Post-decision impact | Level | State | Evidence and decision effect | Acceptance |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The seven-day token expiry is superseded for shared-link tokens; permanence means the bearer token is non-expiring. | `verified` | `resolved` | Directly selected by `DEC-001`; `INV-001` is intentionally superseded for this token class. | `AC-001` |
| `IMP-002` | Permission-change revocation remains mandatory for non-expiring tokens. | `verified` | `mitigated` | Explicitly preserved by `DEC-001` and `INV-002`. | `AC-002` |
| `IMP-003` | Key rotation must not invalidate a non-expiring token; rollover verification and durable revocation state must support rotated keys while active signing keys continue rotating every 90 days. | `verified` | `mitigated` | Explicitly selected by `DEC-001`; `INV-003` remains in force, but the concrete rollover mechanism is not supplied. | `AC-003` |
| `IMP-004` | Links do not automatically survive every lifecycle event: permission changes and explicit revoke events end access, while deleted-resource/account behavior remains unspecified. | `unknown` | `deferred` | `DEC-001` selects revocation triggers but does not decide deletion handling. | `AC-004` |
| `IMP-005` | A disclosed bearer token can provide access indefinitely until a permission-change or explicit revoke event occurs. | `verified` | `accepted` | Non-expiring selection plus explicit exposure acceptance in `DEC-001`. | `AC-005` |
| `IMP-006` | Revocation state must survive key rotation; an old or newly rotated key must not resurrect a revoked token. | `verified` | `detected` | Combined explicit revocation and key-rotation choice in `DEC-001`. | `AC-006` |
| `IMP-007` | Revoke-event delivery or processing failure can extend the accepted exposure window, so revoke processing needs an observable lifecycle. | `inferred` | `detected` | Consequence of removing expiry while relying on explicit events; event guarantees are not supplied. | `AC-007` |

## Delta

- `resolved`: `IMP-001`
- `mitigated`: `IMP-002`, `IMP-003`
- `unchanged`: none
- `accepted`: `IMP-005`
- `deferred`: `IMP-004`
- `blocked`: none
- `new`: `IMP-005`, `IMP-006`, `IMP-007`

The categories are disjoint and exhaustive over the post-decision impact set; `IMP-005`–`IMP-007` are new impacts introduced by the selected policy.

## Acceptance criteria after decision

| ID | Observable criterion | Traceability |
| --- | --- | --- |
| `AC-001` | A shared-link bearer token remains usable after seven days with no time-based expiry. | Resolves `IMP-001`; `DEC-001` |
| `AC-002` | A permission change revokes the active token and prevents subsequent access. | Mitigates `IMP-002`; `DEC-001` |
| `AC-003` | A token issued before a 90-day key rotation remains verifiable after rotation without disabling rotation. | Mitigates `IMP-003`; `DEC-001` |
| `AC-004` | Deleted-resource/account behavior is separately documented and cannot silently contradict the revoke contract. | Deferred `IMP-004`; decision gap remains visible |
| `AC-005` | The security contract records that a disclosed bearer token may remain usable until an explicit revoke event, and this exposure is accepted. | Accepted `IMP-005`; `DEC-001` |
| `AC-006` | Revocation records survive signing-key rotation and a revoked token is rejected under old and new keys. | New `IMP-006` |
| `AC-007` | Revoke events have a traceable lifecycle; delivery or processing failures do not silently disappear. | New `IMP-007` |

## Stop check

`DEC-001` is explicit and every known impact has been recalculated exactly once. Accepted risk remains visible, resolved status has evidence/decision support, and unknown evidence is not presented as verified. This is a report-only planning handoff; no implementation plan, task breakdown, or repository edit is produced.
