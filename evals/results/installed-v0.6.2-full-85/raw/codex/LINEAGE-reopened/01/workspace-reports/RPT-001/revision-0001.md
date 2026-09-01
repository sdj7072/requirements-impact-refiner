# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | profile.displayName and decodeDisplayName are removed from the mobile profile contract. | An older mobile client could still request or decode displayName after the server stops providing it. | Mobile clients using ProfileDecoder.decodeDisplayName. | Removal occurs before the compatibility release has elapsed. | high | Preserve profile.displayName for the configured one release, then remove decodeDisplayName. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove profile.displayName support beginning at mobile/ProfileDecoder.swift's decodeDisplayName only after the one preserved release configured by migrations/profile_field.py. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The current mobile decoder reads profile.displayName through decodeDisplayName and tolerates a missing value as nil. | verified | mobile/ProfileDecoder.swift defines decodeDisplayName(payload:) -&gt; String? and returns payload["displayName"]. |
| `INV-002` | profile.displayName remains preserved for one release before removal. | verified | migrations/profile_field.py names FIELD = "profile.displayName" and sets PRESERVE_RELEASES = 1. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | mobile/ProfileDecoder.swift defines decodeDisplayName(payload:) -&gt; String? and returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-001` | migrations/profile_field.py names FIELD = "profile.displayName" and sets PRESERVE_RELEASES = 1. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | accepted | unknown | The supplied source locations verify the decoder dependency and one-release setting, but the promoted scan's graph evidence is lexical and ends at a provider-unavailable frontier, so transitive client coverage is not independently verified. | `INV-001`, `INV-002` | `DEC-001` | `AC-001` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Accept the one-release preservation window and remove mobile profile.displayName decoding after it elapses. | `REQ-001` | `IMP-001` | The request selects removal and identifies migrations/profile_field.py's PRESERVE_RELEASES = 1 as sufficient compatibility evidence. |

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
| new | `IMP-001` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Remove profile.displayName support beginning at mobile/ProfileDecoder.swift's decodeDisplayName only after the one preserved release configured by migrations/profile_field.py. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | profile.displayName remains available for one release, and decodeDisplayName plus its profile.displayName mapping are removed only after that window. | migrations/profile_field.py establishes the one-release boundary; mobile/ProfileDecoder.swift identifies the client removal point. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| mobile/ProfileDecoder.swift at decodeDisplayName | decodeDisplayName reads payload["displayName"] and decodedField names profile.displayName. | verified |
| migrations/profile_field.py | FIELD is profile.displayName and PRESERVE_RELEASES is 1. | verified |
| Transitive repository coverage | Fast Scan returned a lexical migration-to-decoder path and a provider-unavailable frontier. | unknown beyond the supplied source locations |
| Graph paths for IMP-001 | This impact relies on the supplied, directly inspected decoder and migration evidence; graph coverage beyond those locations is unknown because providers were unavailable. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 9ae16a79f32cff453377820f677b2639; sha256 bdd5fa3e4cd300f8342f0883d76d71efddefac2a4d035b7b9a2c3a883b9cc727; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `DEC-001` | `IMP-001` | `AC-001` | Ready for planning. The one-release compatibility policy is accepted from the supplied evidence; implementation must preserve that ordering, while transitive coverage remains limited to the inspected source locations. |
