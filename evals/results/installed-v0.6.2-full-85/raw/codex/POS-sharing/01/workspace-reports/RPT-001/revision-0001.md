# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | sharing.link token lifetime | A remaining expiry value or generated expiry claim would continue to reject links after seven days. | Existing and newly issued sharing links whose validation reads share/tokens.py. | Validation occurs more than seven days after token issuance. | high | Represent the lifetime as explicitly non-expiring and test validation beyond the old boundary. | refining |
| `IMP-002` | Permanent sharing.link validity | Removing time expiry could accidentally bypass the remaining authorization revocation boundary. | Owners and recipients of links after sharing permissions are reduced or removed. | A permission change occurs after a token has been issued. | critical | Keep REVOKE_ON_PERMISSION_CHANGE enabled and verify that an otherwise non-expiring token is rejected after a permission change. | refining |
| `IMP-003` | Permanent sharing.link validity across signing-key rotation | Tokens may become unverifiable at rotation, making “permanent” mean at most 90 days, or retaining keys indefinitely may enlarge the compromise window. | Every sharing.link token issued before a signing-key rotation. | The active signing key rotates or a retired key is removed. | critical | Choose and document rotation semantics, then test tokens issued before and validated after rotation. | blocked |
| `IMP-004` | sharing.link token lifetime | A leaked token remains usable indefinitely while permissions remain unchanged. | Resources accessible through copied, logged, forwarded, or otherwise exposed sharing links. | A token is disclosed and the owner does not change the corresponding permission. | high | Preserve explicit revocation and decide whether an additional manual revocation mechanism or documented risk acceptance is required. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Make sharing.link tokens in share/tokens.py permanent. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Make sharing.link tokens non-expiring by age while preserving revocation when permissions change. The required behavior across the 90-day signing-key rotation must be selected before implementation because discarding old verification keys would still invalidate otherwise permanent tokens. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | sharing.link tokens currently expire after 7 days. | verified | share/tokens.py defines TOKEN = "sharing.link" and EXPIRY_DAYS = 7. |
| `INV-002` | A sharing.link token is revoked when the associated permission changes. | verified | share/revoke.py defines REVOKE_ON_PERMISSION_CHANGE = True for TOKEN_REF = "sharing.link". |
| `INV-003` | Signing keys rotate every 90 days. | verified | crypto/rotation.py defines SIGNING_KEY_ROTATION_DAYS = 90 for TOKEN_LINK = "sharing.link"; the repository does not state whether prior verification keys are retained. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003`, `IMP-004` | share/tokens.py defines TOKEN = "sharing.link" and EXPIRY_DAYS = 7. |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-004` | share/revoke.py defines REVOKE_ON_PERMISSION_CHANGE = True for TOKEN_REF = "sharing.link". |
| `INV-003` | `REQ-001` | `IMP-003` | crypto/rotation.py defines SIGNING_KEY_ROTATION_DAYS = 90 for TOKEN_LINK = "sharing.link"; the repository does not state whether prior verification keys are retained. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | high | refining | unknown | The supplied source evidence verifies the 7-day setting; PATH-002 is provider-fallback graph evidence and does not expose issuance/validation implementation. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | authorization/privacy | critical | refining | unknown | The supplied source evidence verifies permission-change revocation; PATH-001 is provider-fallback graph evidence connecting crypto/rotation.py to share/revoke.py. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | authorization/privacy | critical | blocked | unknown | crypto/rotation.py establishes a 90-day signing-key rotation, but no evidence defines retention of old verification keys. PATH-002 is provider-fallback graph evidence. | `INV-003`, `INV-001` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | authorization/privacy | high | refining | unknown | Eliminating automatic expiry may extend the useful life of copied or leaked sharing tokens; the supplied evidence identifies permission-change revocation as a compensating control, while both graph paths come from provider fallback. | `INV-001`, `INV-002` | the pending decision | `AC-004` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What should “permanent” mean when signing keys rotate every 90 days? | Valid until explicitly revoked, including across routine key rotations. | `IMP-003`, `IMP-004` | Matches the ordinary meaning of permanent, but requires retaining old verification capability or adopting a rotation-independent token design; compromised credentials need explicit revocation. |
| What should “permanent” mean when signing keys rotate every 90 days? | No EXPIRY_DAYS limit, but allow key rotation to invalidate older tokens. | `IMP-003` | Smallest change in share/tokens.py, but tokens are not actually permanent and may stop working after rotation. |
| What should “permanent” mean when signing keys rotate every 90 days? | Keep the stable link permanent while transparently replacing its signed credential. | `IMP-003`, `IMP-004` | Preserves the user-visible URL across rotations without retaining old signing keys indefinitely, but requires indirection or reissuance beyond the current files. |

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
| new | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Make sharing.link tokens non-expiring by age while preserving revocation when permissions change. The required behavior across the 90-day signing-key rotation must be selected before implementation because discarding old verification keys would still invalidate otherwise permanent tokens. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | A sharing.link token remains valid beyond 7 days when no revocation condition occurs. | Test token validation immediately after issuance and after simulated time greater than seven days. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | A sharing.link token is rejected after its associated permission changes, regardless of its non-expiring age policy. | Test the same token before and after a permission change. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | Token behavior after a 90-day signing-key rotation exactly matches the selected permanence option and is covered by a pre-/post-rotation test. | Exercise a token signed before rotation against verification state after rotation. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-002` | The permanent-token threat model and supported revocation path are documented, and tests prove revocation terminates access. | Review documentation and automated revocation coverage. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-003` | blocked | Implementation cannot guarantee permanence until behavior across routine signing-key rotation is selected. | none | Product/security owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| share/tokens.py token lifetime configuration | Directly named by the request and defines EXPIRY_DAYS = 7 for sharing.link. | verified |
| share/revoke.py permission-change invalidation | Defines the explicit revocation control for sharing.link. | verified |
| crypto/rotation.py signing-key lifecycle | Defines a 90-day signing-key rotation linked to sharing.link, but not retired-key retention behavior. | verified configuration; runtime effect unknown |
| Graph paths for IMP-001 | PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Graph paths for IMP-002 | PATH-001: crypto/rotation.py → share/revoke.py | PATH-001: provider builtin; confidence lexical; location crypto/rotation.py + share/revoke.py |
| Graph paths for IMP-003 | PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Graph paths for IMP-004 | PATH-001: crypto/rotation.py → share/revoke.py &#124;&#124; PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-001: provider builtin; confidence lexical; location crypto/rotation.py + share/revoke.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 9b9e4edcd42a65b985039883d168c600; sha256 92c9bebb466d8912e45529c449c2d63c9ebbb23520df897f696d5d5d28f6f949; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | `IMP-003` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Not ready |
