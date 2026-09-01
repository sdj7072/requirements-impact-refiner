# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Remove the fixed seven-day lifetime for sharing.link tokens. | An inappropriate permanent sentinel could break consumers or still be interpreted as an expiry. | Token issuance and validation code consuming EXPIRY_DAYS. | Creating or validating a sharing.link token after seven days. | high | Use the repository-supported non-expiring representation and verify it with tests or direct configuration assertions. | blocked |
| `IMP-002` | Clarify whether permanent tokens remain revocable when permissions change. | Disabling revocation could preserve access after the owner removes a recipient's permission. | Owners, recipients, and resources protected by sharing.link tokens. | A permission change after a token has been issued. | critical | Preserve permission-change revocation unless the user explicitly requires irrevocable links and accepts the authorization risk. | blocked |
| `IMP-003` | Clarify whether permanent tokens must remain valid across signing-key rotation. | Tokens may cease validating after rotation, or retaining old keys indefinitely may enlarge compromise exposure. | All outstanding sharing.link tokens and signing-key operations. | A signing-key rotation after token issuance. | critical | Explicitly choose rotation compatibility and retain verification material only for the intended token lifetime. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Make sharing.link tokens in share/tokens.py permanent. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Define the lifetime semantics of sharing.link tokens, then update the repository so those tokens have no unintended time-based expiry while explicitly preserving or changing permission-change revocation and signing-key-rotation behavior according to the selected permanence boundary. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The token type remains identified as sharing.link across token, revocation, and signing-key rotation configuration. | verified | share/tokens.py declares TOKEN = "sharing.link"; share/revoke.py and crypto/rotation.py reference the same token string. |
| `INV-002` | Security-sensitive invalidation semantics must be explicit: permission changes and signing-key rotation must not be silently reinterpreted by changing only the nominal expiry. | verified | share/revoke.py enables REVOKE_ON_PERMISSION_CHANGE and crypto/rotation.py sets SIGNING_KEY_ROTATION_DAYS = 90. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | share/tokens.py declares TOKEN = "sharing.link"; share/revoke.py and crypto/rotation.py reference the same token string. |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-003` | share/revoke.py enables REVOKE_ON_PERMISSION_CHANGE and crypto/rotation.py sets SIGNING_KEY_ROTATION_DAYS = 90. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | high | blocked | unknown | share/tokens.py directly sets EXPIRY_DAYS = 7 for TOKEN = "sharing.link"; provider-backed cross-file verification was unavailable. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | authorization/privacy | critical | blocked | unknown | share/revoke.py directly sets REVOKE_ON_PERMISSION_CHANGE = True for sharing.link; provider-backed cross-file verification was unavailable. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | authorization/privacy | critical | blocked | unknown | crypto/rotation.py directly sets SIGNING_KEY_ROTATION_DAYS = 90 for sharing.link; provider-backed cross-file verification was unavailable. | `INV-002` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What should “permanent” mean for sharing.link tokens? | No time expiry, but keep permission-change revocation and existing signing-key rotation semantics. | `IMP-001`, `IMP-002`, `IMP-003` | Safest interpretation: links do not expire merely with age, but authorization changes or cryptographic lifecycle events can still invalidate them. |
| What should “permanent” mean for sharing.link tokens? | No time expiry and survive signing-key rotation, but keep permission-change revocation. | `IMP-001`, `IMP-002`, `IMP-003` | Links remain usable indefinitely while access is authorized, but the system must retain or migrate verification capability across rotations. |
| What should “permanent” mean for sharing.link tokens? | Irrevocable and valid indefinitely, including across permission changes and key rotations. | `IMP-001`, `IMP-002`, `IMP-003` | Strongest permanence, with critical authorization and key-compromise risks because issued links cannot be invalidated through normal controls. |

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
| `REQ-001` | Define the lifetime semantics of sharing.link tokens, then update the repository so those tokens have no unintended time-based expiry while explicitly preserving or changing permission-change revocation and signing-key-rotation behavior according to the selected permanence boundary. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | A sharing.link token is not rejected solely because a fixed number of days has elapsed since issuance. | Verify the non-expiring configuration in share/tokens.py and any available tests or consumers. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | After a permission change, token behavior matches the explicitly selected permanence option. | Verify REVOKE_ON_PERMISSION_CHANGE and any permission-change validation path. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-002` | After signing-key rotation, outstanding token behavior matches the explicitly selected permanence option. | Verify SIGNING_KEY_ROTATION_DAYS and the intended handling of previously signed tokens. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The correct no-expiry representation is not established by the supplied configuration-only repository. | none | requester |
| `IMP-002` | blocked | The word permanent does not determine whether authorization changes should revoke existing links. | none | requester |
| `IMP-003` | blocked | The word permanent does not determine whether links must survive signing-key rotation. | none | requester |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| share/tokens.py token lifetime configuration | EXPIRY_DAYS is set to 7 next to TOKEN = "sharing.link". | high |
| share/revoke.py permission-change invalidation | REVOKE_ON_PERMISSION_CHANGE is True and TOKEN_REF is sharing.link. | high |
| crypto/rotation.py cryptographic lifecycle | SIGNING_KEY_ROTATION_DAYS is 90 and TOKEN_LINK is sharing.link. | high |
| Graph paths for IMP-001 | PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Graph paths for IMP-002 | PATH-001: crypto/rotation.py → share/revoke.py | PATH-001: provider builtin; confidence lexical; location crypto/rotation.py + share/revoke.py |
| Graph paths for IMP-003 | PATH-001: crypto/rotation.py → share/revoke.py &#124;&#124; PATH-002: crypto/rotation.py → sensitive-sha256-9c63ebfab69e182f2c63a0f75264aa49c7fbf3951972e6fa0ed6fc3031c832e8 | PATH-001: provider builtin; confidence lexical; location crypto/rotation.py + share/revoke.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location crypto/rotation.py + share/tokens.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt ca05a55d54016b6caddd9d0d09ba149e; sha256 e7d0571701142675c1f366a2123377af5117f6c33d5a1346a3f3ae4bc8277bdb; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
