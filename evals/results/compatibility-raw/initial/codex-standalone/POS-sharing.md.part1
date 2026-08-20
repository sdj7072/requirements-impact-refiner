# Requirements Impact Refinement — Permanent shared links

## Status

`NEEDS_DECISION` — the request is under-specified. No option has been selected; no implementation plan or repository edit is proposed.

## Requirement revision

`REQ-001`: Make shared links permanent, while defining whether “permanent” means a stable link address, non-expiring bearer access, or both. The existing seven-day token expiry, permission-change revocation, and 90-day signing-key rotation remain compatibility constraints until a policy is selected.

## Current behavior and preserved invariants

| ID | Current behavior / invariant | Evidence | Level | Relationship |
| --- | --- | --- | --- | --- |
| `INV-001` | Share tokens expire after seven days. | Supplied fact: share tokens currently expire after seven days. | `verified` | `must-preserve` or explicitly supersede through the decision for `REQ-001` |
| `INV-002` | Permission changes revoke active share tokens. | Supplied fact: permission changes revoke active tokens. | `verified` | `must-preserve` unless the selected policy explicitly changes revocation semantics |
| `INV-003` | Token signing keys rotate every 90 days. | Supplied fact: token signing keys rotate every 90 days. | `verified` | `must-preserve` `REQ-001` |

## Impact ledger

| ID | Impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | “Permanent” conflicts with the current seven-day expiry unless the requirement means a stable URL whose access credential can be renewed, or explicitly authorizes non-expiring access. | `verified` | `refining` | Requested permanent links plus the supplied seven-day expiry. | `affects` `REQ-001`, `INV-001`; `produces` `AC-001` |
| `IMP-002` | A non-expiring bearer token must still honor permission-change revocation; otherwise a previously shared link can continue granting access after authorization is withdrawn. | `verified` | `detected` | Supplied active-token revocation behavior. | `affects` `REQ-001`, `INV-002`; `produces` `AC-002` |
| `IMP-003` | Tokens that outlive a 90-day signing-key rotation require a key-version/history or re-issuance policy; otherwise “permanent” links will break at rotation or force unsafe indefinite key retention. | `verified` | `blocked` | Supplied 90-day signing-key rotation; retention/verification behavior is not supplied. | `affects` `REQ-001`, `INV-003`; `produces` `AC-003` |
| `IMP-004` | The request does not establish whether a permanent link should survive owner deletion, resource deletion, permission changes, or manual revocation, nor whether access is public or still authorization-checked. | `unknown` | `blocked` | No lifecycle, audience, or revocation contract supplied. | `affects` `REQ-001`; `produces` `AC-004` |

## One focused decision

What should “make shared links permanent” mean for the link’s address, access credential, revocation, and signing-key rotation?

1. **Permanent URL with renewable, revocable access (recommended)** — keep a stable share record/URL indefinitely, but issue or refresh access credentials under the existing authorization checks; permission changes and explicit revocation continue to invalidate access, and signing-key rotation remains supported without making the URL change. This preserves security invariants while making the shared address permanent.
2. **Long-lived token with retained verification history** — make the bearer token itself non-expiring, retain enough signing-key versions or key metadata to verify it across 90-day rotations, and maintain an explicit revocation mechanism for permission changes and manual revocation. This provides durable offline-friendly access but increases bearer-token exposure and key/revocation state.
3. **Non-expiring public bearer link** — remove the seven-day expiry and permit the token to remain valid across key rotations, with only explicit revocation ending access. This maximizes link permanence but changes the current authorization and exposure model; the treatment of permission changes and deleted resources must be explicitly accepted.

Please select one option, or specify another policy covering stable URL versus token lifetime, permission-change revocation, key rotation, and resource/account deletion. No decision has been recorded; no implementation tasks or plan are produced.

## Recorded decision

Decision needed — no `DEC-###` is recorded because no user/stakeholder option has been selected.

## Whole-set recalculation (before decision)

All supplied impacts have been checked against the permanence request. No impact is resolved, mitigated, accepted, deferred, or new before the focused policy decision.

## Delta

- `resolved`: none
- `mitigated`: none
- `unchanged`: `IMP-001`, `IMP-002`
- `accepted`: none
- `deferred`: none
- `blocked`: `IMP-003`, `IMP-004`
- `new`: none

## Stop check and planning handoff

Stopped at the single required permanence-policy decision. The refined requirement, preserved invariants, evidence-backed impacts, and provisional acceptance-criteria targets are ready for continuation after selection; no implementation plan, tasks, or repository edit is included.

### Acceptance criteria targets

| ID | Future criterion | Evidence / gap |
| --- | --- | --- |
| `AC-001` | The selected meaning of “permanent” is explicit: URL lifetime and access-credential lifetime are independently testable. | Produced by `IMP-001`; permanence semantics are not supplied. |
| `AC-002` | Permission changes and explicit revocation follow the selected policy and cannot leave unauthorized active access. | Produced by `IMP-002`; revocation behavior for any new credential model is not supplied. |
| `AC-003` | A link remains verifiable or safely renewable across each 90-day signing-key rotation without unsafe indefinite key retention. | Produced by blocked `IMP-003`; key-history and rollover contract is unavailable. |
| `AC-004` | Lifecycle behavior for deleted resources/accounts, changed permissions, and manual revocation is explicit and testable. | Produced by blocked `IMP-004`; sharing lifecycle and audience policy are unavailable. |

---

## Decision response and recalculation

### Recorded decision

`DEC-001`: **Option 3 — Non-expiring public bearer link.** The share token is non-expiring and remains valid across the 90-day signing-key rotation. Permission changes continue to revoke active tokens, and an explicit revoke event is the authoritative way to end access. The requester explicitly accepts the exposure of a non-expiring bearer link until an explicit revoke event; this acceptance does not waive permission-change revocation or key-rotation compatibility.

### Revised requirement

`REQ-001` (revised): Shared links use non-expiring bearer tokens. Tokens remain verifiable across signing-key rotation, and permission changes revoke active tokens. Access remains available until a permission-change or explicit revoke event; the accepted exposure window is the period before such an event is emitted or processed. No additional expiry-based revocation is implied.

### Disjoint lifecycle recalculation

| ID | Post-decision impact | Level | State | Decision effect / evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-001` | The seven-day token expiry is superseded for shared-link tokens; permanence now means the bearer token itself is non-expiring. | `verified` | `resolved` | Directly selected by `DEC-001`; supplied seven-day expiry is intentionally changed. | `affects` `REQ-001`, `INV-001`; `resolved-by` `DEC-001` |
| `IMP-002` | Permission-change revocation remains mandatory for non-expiring tokens; otherwise access would survive an authorization withdrawal. | `verified` | `mitigated` | Explicitly preserved by `DEC-001`; supplied active-token revocation invariant remains in force. | `affects` `REQ-001`, `INV-002`; `mitigated-by` `DEC-001` |
| `IMP-003` | Key rotation must not invalidate a non-expiring token; verification must support rotated signing keys or an equivalent rollover mechanism while continuing to rotate the active signing key. | `verified` | `mitigated` | Explicitly selected by `DEC-001`; the 90-day rotation fact is preserved, but the concrete key-history/rollover mechanism remains an implementation detail. | `affects` `REQ-001`, `INV-003`; `mitigated-by` `DEC-001` |
| `IMP-004` | The selected contract does not make links survive every lifecycle event: permission changes and explicit revoke events end access, while behavior for deleted resources/accounts remains outside the supplied decision. | `unknown` | `deferred` | `DEC-001` defines revocation triggers but does not select deletion handling. | `affects` `REQ-001`; `deferred-by` `DEC-001` |

### New impacts introduced by the decision

| ID | New impact | Level | State | Evidence | Links |
| --- | --- | --- | --- | --- | --- |
| `IMP-005` | A stolen or unintentionally disclosed bearer token can provide access indefinitely until a permission-change or explicit revoke event occurs. | `verified` | `accepted` | Non-expiring bearer-token selection plus explicit exposure acceptance in `DEC-001`. | `affects` `REQ-001`; `accepted-by` `DEC-001`; `produces` `AC-005` |
| `IMP-006` | Revocation state must remain effective after signing-key rotation; rotating the key cannot resurrect a token revoked by a permission-change or explicit revoke event. | `verified` | `detected` | Combined selected revocation and key-rotation semantics in `DEC-001`. | `affects` `REQ-001`, `INV-002`, `INV-003`; `produces` `AC-006` |
| `IMP-007` | Because expiry no longer limits access, delivery and processing failures for revoke events extend the accepted exposure window and require an observable revoke lifecycle. | `inferred` | `detected` | Consequence of removing seven-day expiry while relying on explicit revoke events; event delivery semantics are not supplied. | `affects` `REQ-001`; `produces` `AC-007` |

### Delta

- `resolved`: `IMP-001`
- `mitigated`: `IMP-002`, `IMP-003`
- `unchanged`: none
- `accepted`: `IMP-005` (indefinite bearer-token exposure until an explicit revoke event)
- `deferred`: `IMP-004` (deleted-resource/account lifecycle)
- `blocked`: none
- `new`: `IMP-005`, `IMP-006`, `IMP-007`

### Acceptance criteria after decision

| ID | Criterion | Traceability |
| --- | --- | --- |
| `AC-001` | A shared-link bearer token has no time-based expiry and remains usable after seven days. | Resolves `IMP-001`; `DEC-001` |
| `AC-002` | A permission change revokes the active token and prevents subsequent access. | Mitigates `IMP-002`; `DEC-001` |
| `AC-003` | A token issued before a 90-day signing-key rotation remains verifiable after rotation without disabling key rotation. | Mitigates `IMP-003`; `DEC-001` |
| `AC-004` | The behavior for deleted resources/accounts is separately documented; deletion or permission changes do not silently contradict the selected revoke contract. | Deferred `IMP-004`; decision gap remains visible |
| `AC-005` | The product/security contract visibly records that a disclosed bearer token may remain usable until an explicit revoke event; this exposure is accepted for `DEC-001`. | Accepted `IMP-005`; `DEC-001` |
| `AC-006` | Revocation records survive signing-key rotation and a revoked token cannot be accepted under an older or newly rotated key. | New `IMP-006` |
| `AC-007` | Revoke events have a traceable lifecycle sufficient to determine when access was actually stopped; failures do not silently disappear. | New `IMP-007` |

## Stop check

Decision `DEC-001` is recorded and the full impact set has been recalculated. This response stops at the refined requirement and acceptance criteria; no implementation plan, tasks, or repository edit is included.
