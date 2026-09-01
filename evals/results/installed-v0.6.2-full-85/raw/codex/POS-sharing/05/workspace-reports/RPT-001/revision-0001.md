# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Elapsed-time validity of sharing.link tokens | Changing only the seven-day constant may not express an unbounded lifetime in the token API or may leave hidden expiry assumptions untested. | Existing and newly issued sharing.link tokens, plus their validation behavior | A token is validated more than seven days after issuance | high | Use the repository’s supported non-expiring representation and verify validation beyond the former boundary. | refining |
| `IMP-002` | Permanence across permission changes | If permanence disables permission-change revocation, a previously shared link can retain access after its owner or administrator removes permission. | Resource owners, administrators, link recipients, and protected shared content | Permissions change after a sharing.link token has been issued | critical | Select and test an explicit permission-change invalidation policy; retaining revocation is the safer default. | blocked |
| `IMP-003` | Permanence across signing-key rotation | A nominally non-expiring token may stop verifying at rotation, or retaining old keys forever may enlarge the impact of a compromised signing key. | Long-lived link holders and operators responsible for key lifecycle and incident response | The signing key rotates after a sharing.link token is issued | critical | Choose a rotation survival policy, define verification-key retention/re-signing behavior, and test tokens across rotation. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Make sharing.link tokens in share/tokens.py permanent. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Make sharing.link tokens non-expiring by elapsed time. Before implementation, define whether “permanent” also requires tokens to survive permission changes and signing-key rotation, because the supplied repository evidence shows those independent invalidation boundaries. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | sharing.link tokens currently have a seven-day time limit. | verified | share/tokens.py defines TOKEN = "sharing.link" and EXPIRY_DAYS = 7. |
| `INV-002` | Tokens are currently configured to be revoked when permissions change. | verified | share/revoke.py defines REVOKE_ON_PERMISSION_CHANGE = True for TOKEN_REF = "sharing.link". |
| `INV-003` | Signing keys currently rotate every 90 days. | verified | crypto/rotation.py defines SIGNING_KEY_ROTATION_DAYS = 90 and TOKEN_LINK = "sharing.link"; the available code does not show whether old verification keys are retained. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | share/tokens.py defines TOKEN = "sharing.link" and EXPIRY_DAYS = 7. |
| `INV-002` | `REQ-001` | `IMP-002` | share/revoke.py defines REVOKE_ON_PERMISSION_CHANGE = True for TOKEN_REF = "sharing.link". |
| `INV-003` | `REQ-001` | `IMP-003` | crypto/rotation.py defines SIGNING_KEY_ROTATION_DAYS = 90 and TOKEN_LINK = "sharing.link"; the available code does not show whether old verification keys are retained. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | high | refining | unknown | share/tokens.py directly sets EXPIRY_DAYS = 7 for sharing.link; provider-backed transitive confirmation was unavailable and the promoted graph path is fallback-only. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | authorization/privacy | critical | blocked | unknown | share/revoke.py directly configures REVOKE_ON_PERMISSION_CHANGE = True for sharing.link; provider-backed transitive confirmation was unavailable and the promoted graph path is fallback-only. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | authorization/privacy | critical | blocked | unknown | crypto/rotation.py sets a 90-day signing-key rotation interval for sharing.link, but the supplied files do not establish old-key retention or token verification behavior after rotation; provider-backed transitive confirmation was unavailable. | `INV-003` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What should “permanent” mean for sharing.link tokens beyond removing the seven-day expiry? | No elapsed-time expiry; keep revocation on permission changes and allow signing-key lifecycle policy to invalidate tokens. | `IMP-002`, `IMP-003` | Recommended security boundary: links last indefinitely during stable authorization/key state, but are intentionally not irrevocable. |
| What should “permanent” mean for sharing.link tokens beyond removing the seven-day expiry? | No elapsed-time expiry and survive signing-key rotation; keep revocation on permission changes. | `IMP-002`, `IMP-003` | Links remain durable through routine rotation, requiring explicit old-key retention or token migration while preserving authorization revocation. |
| What should “permanent” mean for sharing.link tokens beyond removing the seven-day expiry? | Survive elapsed time, permission changes, and signing-key rotation. | `IMP-002`, `IMP-003` | Strongest permanence, but permission removal and routine key retirement cannot invalidate access; this creates critical authorization and key-compromise risk and needs a separate emergency revocation design. |

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
| `REQ-001` | Make sharing.link tokens non-expiring by elapsed time. Before implementation, define whether “permanent” also requires tokens to survive permission changes and signing-key rotation, because the supplied repository evidence shows those independent invalidation boundaries. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | A sharing.link token remains valid after the former seven-day boundary when no selected invalidation event occurs. | Directly verifies the requested change against EXPIRY_DAYS = 7. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | A test demonstrates the selected validity outcome immediately after a permission change. | Required because REVOKE_ON_PERMISSION_CHANGE is an independent current invalidation path. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | A test demonstrates the selected validity outcome after signing-key rotation and documents any old-key retention or token migration behavior. | Required because rotation is configured at 90 days but post-rotation verification behavior is absent from the supplied code. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-002` | blocked | The request does not state whether permanent links override permission-change revocation. | none | Requester/product security owner |
| `IMP-003` | blocked | The request does not state whether permanent links must survive signing-key rotation, and old-key verification behavior is not evidenced. | none | Requester/security and key-management owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| share/tokens.py elapsed-time configuration for TOKEN = "sharing.link" | Direct file inspection shows EXPIRY_DAYS = 7. | high |
| share/revoke.py permission-change invalidation for sharing.link | Direct file inspection shows REVOKE_ON_PERMISSION_CHANGE = True. | high |
| crypto/rotation.py signing-key lifecycle for sharing.link | Direct file inspection shows SIGNING_KEY_ROTATION_DAYS = 90; retention and validation code are not present. | medium for impact, unknown for post-rotation behavior |
| Tests and consumers | The workspace contains only the three supplied Python files and no tests or token implementation beyond constants. | unknown; additional integration behavior may exist outside this repository snapshot |
| Graph paths for IMP-001 | PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Graph paths for IMP-002 | PATH-001: crypto/rotation.py → share/revoke.py | PATH-001: provider builtin; confidence lexical; location crypto/rotation.py + share/revoke.py |
| Graph paths for IMP-003 | PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt a15982462acd56c8a5ccd39a2d73f8b4; sha256 bac8edb37d93ef9853db33b3676f88aad26cc984c0f06a862b4fb80868a1fd4a; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
