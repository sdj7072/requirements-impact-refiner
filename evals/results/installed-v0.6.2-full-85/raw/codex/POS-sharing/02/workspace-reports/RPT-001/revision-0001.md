# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | sharing.link token lifetime | Tokens would still stop working after seven days if the expiry value is left numeric or interpreted as a duration. | Anyone using a sharing.link more than seven days after issuance. | Token validation checks the configured expiry age. | high | Set EXPIRY_DAYS to the repository's no-expiry sentinel and verify the definition. | detected |
| `IMP-002` | sharing.link token lifetime | Treating permanent as irrevocable could let a link retain access after its permission is withdrawn. | Owners and recipients of resources shared through sharing.link. | A resource permission changes after a token is issued. | critical | Leave REVOKE_ON_PERMISSION_CHANGE enabled and unchanged. | mitigated |
| `IMP-003` | sharing.link token lifetime | A token without an expiry claim may still become unverifiable after signing-key rotation if old verification keys are discarded. | Holders of older sharing.link tokens. | Signing-key rotation and retirement of the key that signed the token. | high | Keep rotation unchanged in this scoped edit and document that permanent means no fixed age expiry, not guaranteed validity across key retirement. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Make sharing.link tokens in share/tokens.py permanent. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | For the sharing.link token definition in share/tokens.py, remove the fixed seven-day age limit by representing EXPIRY_DAYS as no expiry. Preserve permission-change revocation as an independent security invalidation mechanism, and do not change signing-key rotation policy in this scoped change. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | sharing.link tokens remain revocable when sharing permissions change. | verified | share/revoke.py defines REVOKE_ON_PERMISSION_CHANGE = True and TOKEN_REF = "sharing.link". |
| `INV-002` | The system continues rotating signing keys on its configured schedule; this change does not weaken the rotation policy. | verified | crypto/rotation.py defines SIGNING_KEY_ROTATION_DAYS = 90 and TOKEN_LINK = "sharing.link". |
| `INV-003` | The token identifier remains sharing.link. | verified | share/tokens.py defines TOKEN = "sharing.link". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-002` | share/revoke.py defines REVOKE_ON_PERMISSION_CHANGE = True and TOKEN_REF = "sharing.link". |
| `INV-002` | `REQ-001` | `IMP-003` | crypto/rotation.py defines SIGNING_KEY_ROTATION_DAYS = 90 and TOKEN_LINK = "sharing.link". |
| `INV-003` | `REQ-001` | `IMP-001` | share/tokens.py defines TOKEN = "sharing.link". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | high | detected | unknown | share/tokens.py currently defines EXPIRY_DAYS = 7. The promoted receipt reaches this definition only through lexical/structural fallback evidence because external graph providers were unavailable. | `INV-003` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | authorization/privacy | critical | mitigated | unknown | share/revoke.py explicitly enables REVOKE_ON_PERMISSION_CHANGE for sharing.link. The promoted receipt's transitive relationship is limited to lexical/structural fallback evidence. | `INV-001` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | authorization/privacy | high | accepted | unknown | crypto/rotation.py rotates signing keys every 90 days for sharing.link, but the repository does not show retired-key retention and the promoted receipt used fallback evidence; rotation may remain an independent validity boundary. | `INV-002` | `DEC-001` | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove the fixed age expiry in share/tokens.py while preserving permission-change revocation and signing-key rotation. | `REQ-001` | `IMP-003` | The request explicitly scopes the change to share/tokens.py; the supplied revocation and rotation evidence identifies independent security controls that should not be disabled. |

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
| `REQ-001` | For the sharing.link token definition in share/tokens.py, remove the fixed seven-day age limit by representing EXPIRY_DAYS as no expiry. Preserve permission-change revocation as an independent security invalidation mechanism, and do not change signing-key rotation policy in this scoped change. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-003` | share/tokens.py represents EXPIRY_DAYS as no expiry for sharing.link and no longer uses the value 7. | A direct inspection or focused test of share/tokens.py must show the no-expiry sentinel. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-001` | Permission changes continue to revoke sharing.link tokens. | share/revoke.py remains REVOKE_ON_PERMISSION_CHANGE = True for TOKEN_REF = "sharing.link". |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-002` | The signing-key rotation interval remains 90 days. | crypto/rotation.py remains SIGNING_KEY_ROTATION_DAYS = 90 for TOKEN_LINK = "sharing.link". |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| share/tokens.py sharing.link expiry configuration | TOKEN = "sharing.link" and EXPIRY_DAYS = 7 are present. | verified locally |
| share/revoke.py permission-change revocation | REVOKE_ON_PERMISSION_CHANGE = True and TOKEN_REF = "sharing.link" are present. | verified locally and intentionally unchanged |
| crypto/rotation.py signing-key rotation | SIGNING_KEY_ROTATION_DAYS = 90 and TOKEN_LINK = "sharing.link" are present. | verified configuration; retired-key retention behavior is not represented in this repository |
| Graph paths for IMP-001 | PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Graph paths for IMP-002 | PATH-001: crypto/rotation.py → share/revoke.py | PATH-001: provider builtin; confidence lexical; location crypto/rotation.py + share/revoke.py |
| Graph paths for IMP-003 | PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 2ee05f8ae1a76af973a76b30ebcb7081; sha256 8183ada7f1ddb5bbfce59ba5320b3cd84e7bf9c0cac5463965d4533ebe4ef48e; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Ready. Implement the scoped expiry configuration change, preserve revocation and rotation files, then verify all three acceptance criteria. Graph coverage remains limited because optional providers were unavailable. |
