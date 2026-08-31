# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Remove mobile decoding of profile.displayName. | Clients released before the decoder removal could fail to tolerate an immediate server-side field removal. | Mobile client versions spanning the profile field-removal rollout. | Deployment removes profile.displayName while an older decoder-capable client is still within the supported transition. | high | Keep the migration preservation policy at one release for this field; the supplied evidence supports treating client compatibility as addressed. | accepted |
| `IMP-002` | The mobile profile model will no longer expose a decoded profile.displayName value. | Any remaining consumer expecting the decoded display name could lose visible profile-name behavior. | Mobile profile features that would consume decodeDisplayName. | A consumer remains after decodeDisplayName is removed. | medium | Remove the decoder declaration and verify that no mobile reference to decodeDisplayName, decodedField, or profile.displayName remains. | accepted |
| `IMP-003` | Delete the apparent sole repository decoder for profile.displayName. | An overlooked in-repository call site could fail to compile or silently lose a value. | Repository code that might reference the removed symbol or field. | Removal lands while another tracked source still references the decoder or field. | low | The current text search shows no downstream call site; repeat reference search and compile/test after the edit. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove support for profile.displayName starting at mobile/ProfileDecoder.swift by deleting decodeDisplayName and its decodedField declaration, while relying on the configured one-release migration preservation window to maintain backward client compatibility during rollout. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Before removal, the mobile profile decoder reads the displayName payload key as profile.displayName and returns it as an optional String. | verified | mobile/ProfileDecoder.swift declares decodedField = "profile.displayName" and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | The profile.displayName migration preserves the field for one release during the compatibility transition. | verified | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName"; the supplied migration evidence identifies this as sufficient for client compatibility. |
| `INV-003` | After removal, mobile code must not decode or otherwise depend on profile.displayName. | verified | A repository-wide search currently finds decodeDisplayName/displayName references only in mobile/ProfileDecoder.swift and the migration declaration in migrations/profile_field.py. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | mobile/ProfileDecoder.swift declares decodedField = "profile.displayName" and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-001` | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName"; the supplied migration evidence identifies this as sufficient for client compatibility. |
| `INV-003` | `REQ-001` | `IMP-002`, `IMP-003` | A repository-wide search currently finds decodeDisplayName/displayName references only in mobile/ProfileDecoder.swift and the migration declaration in migrations/profile_field.py. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | accepted | unknown | Direct inspection confirms PRESERVE_RELEASES = 1 and FIELD = "profile.displayName" in the migration file, and the supplied evidence identifies the one-release window as the compatibility resolution. The receipt cannot independently verify external client relationships. | `INV-001`, `INV-002` | `DEC-001` | `AC-002` |
| `IMP-002` | `REQ-001` | functionality | medium | accepted | unknown | Direct inspection confirms mobile/ProfileDecoder.swift implements the display-name decode behavior, and the requested change explicitly removes this profile field beginning at that function. Graph coverage is limited by unavailable providers. | `INV-001`, `INV-003` | `DEC-001` | `AC-001` |
| `IMP-003` | `REQ-001` | regression | low | mitigated | unknown | A repository-wide text search found no decodeDisplayName or displayName consumer outside mobile/ProfileDecoder.swift, but unavailable graph providers leave a coverage frontier. | `INV-003` | `DEC-001` | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove profile.displayName decoding and use the configured one-release preservation window as the client compatibility resolution. | `REQ-001` | `IMP-001`, `IMP-002` | The request selects field removal, and the supplied migration evidence states that PRESERVE_RELEASES = 1 is sufficient to resolve the client compatibility impact. |

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
| `REQ-001` | Remove support for profile.displayName starting at mobile/ProfileDecoder.swift by deleting decodeDisplayName and its decodedField declaration, while relying on the configured one-release migration preservation window to maintain backward client compatibility during rollout. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-002` | `INV-001` | mobile/ProfileDecoder.swift no longer declares decodedField for profile.displayName or decodeDisplayName. | The current declarations are localized to mobile/ProfileDecoder.swift, giving a bounded removal target. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-002` | The profile.displayName migration continues to preserve the field for exactly one release across the decoder-removal rollout. | migrations/profile_field.py currently sets PRESERVE_RELEASES = 1 for FIELD = "profile.displayName". |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | After removal, a repository-wide search finds no mobile reference to decodeDisplayName, decodedField, displayName, or profile.displayName, except the intentional migration metadata retained for the compatibility window. | The pre-change repository-wide search finds relevant source references only in mobile/ProfileDecoder.swift and migrations/profile_field.py. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Mobile decoding behavior in mobile/ProfileDecoder.swift | The file contains decodedField and decodeDisplayName as the concrete removal starting point. | High for direct source; transitive graph confidence remains limited by unavailable providers. |
| Migration compatibility policy in migrations/profile_field.py | The file binds PRESERVE_RELEASES = 1 to FIELD = "profile.displayName". | High for direct source and the user-supplied compatibility interpretation. |
| In-repository downstream references | Text search found no additional consumer beyond the decoder and migration metadata. | Moderate: bounded text evidence exists, but the graph receipt retains an unavailable-provider frontier. |
| Graph paths for IMP-001 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Graph paths for IMP-002 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Graph paths for IMP-003 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt c882d9c30e64f3af8d475bcfd0789688; sha256 df7b6058072de322e3fc6bc74e77de892afdf0c0ed241c19e5d54c1f1d8e5ef7; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002`, `AC-003` | Ready for planning. The explicit decision treats client compatibility as addressed by the supplied one-release preservation evidence, the functionality removal is accepted, and remaining regression risk is mitigated with post-edit reference search and compile/test criteria. |
