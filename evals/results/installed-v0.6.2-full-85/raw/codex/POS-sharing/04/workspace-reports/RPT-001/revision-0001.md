# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | sharing.link token age-based lifetime | A finite expiry value would contradict the requested permanent lifetime. | Links that are more than seven days old. | Validation based on EXPIRY_DAYS after token issuance. | medium | Replace the finite seven-day value with the codebase's no-expiry representation and verify the configured value. | accepted |
| `IMP-002` | meaning of permanent sharing.link tokens | Treating permanent as non-revocable could preserve access after authorization is withdrawn. | Users whose permissions change after a link is issued. | A permission change for an existing token holder. | high | Keep REVOKE_ON_PERMISSION_CHANGE enabled and define permanence as removal of age-based expiry only. | accepted |
| `IMP-003` | meaning of permanent sharing.link tokens | Changing or bypassing key rotation could weaken cryptographic operations, while retiring old keys may still invalidate old tokens. | Tokens signed under rotated or retired keys. | Signing-key rotation or retirement. | high | Leave the 90-day rotation configuration unchanged and do not promise survival across key retirement without verifier evidence. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Make sharing.link tokens in share/tokens.py permanent. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Make sharing.link tokens permanent with respect to elapsed time by removing the finite 7-day expiry in share/tokens.py. Preserve permission-change revocation in share/revoke.py and the existing 90-day signing-key rotation policy in crypto/rotation.py; permanence does not mean immunity from explicit revocation or cryptographic key lifecycle controls. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | sharing.link tokens currently have a finite seven-day age-based expiry. | verified | share/tokens.py contains TOKEN = "sharing.link" and EXPIRY_DAYS = 7. |
| `INV-002` | A permission change continues to revoke sharing.link access. | verified | share/revoke.py contains REVOKE_ON_PERMISSION_CHANGE = True and TOKEN_REF = "sharing.link". |
| `INV-003` | The signing-key lifecycle remains configured for 90-day rotation. | verified | crypto/rotation.py contains SIGNING_KEY_ROTATION_DAYS = 90 and TOKEN_LINK = "sharing.link". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | share/tokens.py contains TOKEN = "sharing.link" and EXPIRY_DAYS = 7. |
| `INV-002` | `REQ-001` | `IMP-002` | share/revoke.py contains REVOKE_ON_PERMISSION_CHANGE = True and TOKEN_REF = "sharing.link". |
| `INV-003` | `REQ-001` | `IMP-003` | crypto/rotation.py contains SIGNING_KEY_ROTATION_DAYS = 90 and TOKEN_LINK = "sharing.link". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | medium | accepted | unknown | The requested token is identified in share/tokens.py and its only configured expiry is EXPIRY_DAYS = 7; provider-backed verification of the scanned transitive path was unavailable. | `INV-001` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | authorization/privacy | high | accepted | unknown | share/revoke.py independently enables revocation on permission change for sharing.link; provider-backed verification of the scanned transitive path was unavailable. | `INV-002` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | authorization/privacy | high | accepted | unknown | crypto/rotation.py associates sharing.link with SIGNING_KEY_ROTATION_DAYS = 90; provider-backed verification of retired-key behavior was unavailable. | `INV-003` | `DEC-001` | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove only elapsed-time expiry; retain permission-change revocation and signing-key rotation. | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | The request explicitly targets EXPIRY_DAYS in share/tokens.py, while the supplied revocation and rotation settings are separate security controls that should remain intact. |

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
| new | `IMP-001`, `IMP-002`, `IMP-003` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Make sharing.link tokens permanent with respect to elapsed time by removing the finite 7-day expiry in share/tokens.py. Preserve permission-change revocation in share/revoke.py and the existing 90-day signing-key rotation policy in crypto/rotation.py; permanence does not mean immunity from explicit revocation or cryptographic key lifecycle controls. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | share/tokens.py no longer configures sharing.link with a finite seven-day expiry and instead uses the repository's no-expiry representation. | Directly verifies the requested behavior change at the named configuration point. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | REVOKE_ON_PERMISSION_CHANGE remains True for sharing.link. | Preserves explicit authorization invalidation despite removal of age-based expiry. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | SIGNING_KEY_ROTATION_DAYS remains 90 for sharing.link. | Preserves the existing cryptographic lifecycle policy. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| share/tokens.py age-based expiry configuration for sharing.link | The request names this file and the file contains EXPIRY_DAYS = 7. | high |
| share/revoke.py permission-change revocation is preserved, not modified | The file independently maps REVOKE_ON_PERMISSION_CHANGE = True to sharing.link. | high |
| crypto/rotation.py signing-key rotation configuration is preserved, not modified | The file maps SIGNING_KEY_ROTATION_DAYS = 90 to sharing.link; downstream retired-key verification is not present in the supplied repository. | medium |
| Graph paths for IMP-001 | PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Graph paths for IMP-002 | PATH-001: crypto/rotation.py → share/revoke.py | PATH-001: provider builtin; confidence lexical; location crypto/rotation.py + share/revoke.py |
| Graph paths for IMP-003 | PATH-001: crypto/rotation.py → share/revoke.py &#124;&#124; PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-001: provider builtin; confidence lexical; location crypto/rotation.py + share/revoke.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 3d0179db97c660feba37127cc4c2da5d; sha256 7c06a42b5f7efda37a5b30309b98dbd3cc6c76fa66c867c9fc16d540c71404d5; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Ready. Implement the no-expiry representation in share/tokens.py only, then verify that revocation and rotation settings remain unchanged. |
