# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Mobile profile display-name decoding is removed. | The client could continue exposing or expecting displayName if the decoder symbol or field constant remains. | The mobile profile decoding path beginning at decodeDisplayName. | Building or running the mobile client after profile.displayName support is removed. | medium | Remove decodeDisplayName and the associated profile.displayName decoder declaration, then verify no mobile reference remains. | detected |
| `IMP-002` | The mobile payload contract no longer consumes profile.displayName. | A producer may continue sending the field, or another consumer may still rely on it during the transition. | Profile payload production and mobile decoding at the profile.displayName boundary. | Profile payloads cross the client boundary during or after the field-removal release. | medium | Keep the one-release migration window and verify the repository no longer contains consumers after removing the decoder. | detected |
| `IMP-003` | The profile field is retired from the mobile decoder. | Previously released clients could fail if the field disappeared without a compatibility interval. | Clients spanning the profile.displayName removal boundary. | Deployment of the field-removal release while a prior client release remains active. | high | Retain PRESERVE_RELEASES = 1; this supplies the requested compatibility mitigation while transitive graph coverage remains provider-limited. | mitigated |
| `IMP-004` | Removal of profile.displayName references from the mobile client. | A stale reference or test fixture could preserve the removed behavior or cause a build/runtime regression. | Mobile code and tests that compile against or decode profile.displayName. | Compiling or testing after the decoder removal. | medium | Search for remaining decodeDisplayName/displayName references and run the mobile verification suite after implementation. | detected |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove support for the profile.displayName field from the mobile client, beginning with decodeDisplayName in mobile/ProfileDecoder.swift, while preserving compatibility for one release as configured by migrations/profile_field.py. Removal must eliminate the decoder behavior without leaving mobile references that still expect displayName. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The current mobile profile decoder reads the displayName payload key and returns it as an optional string. | verified | mobile/ProfileDecoder.swift declares profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | The profile-field migration preserves compatibility for one release. | verified | migrations/profile_field.py sets PRESERVE_RELEASES = 1 for FIELD = "profile.displayName". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-004` | mobile/ProfileDecoder.swift declares profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-003` | migrations/profile_field.py sets PRESERVE_RELEASES = 1 for FIELD = "profile.displayName". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | medium | detected | unknown | The source defines the targeted decoder, while the transitive relation in PATH-001 is lexical and provider-limited. | `INV-001` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | data | medium | detected | unknown | PATH-001 lexically links the profile.displayName migration and mobile decoder; provider fallback leaves transitive producers and consumers unknown. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002` |
| `IMP-003` | `REQ-001` | compatibility | high | mitigated | unknown | Current source verifies PRESERVE_RELEASES = 1 for profile.displayName and the user supplies it as compatibility-resolution evidence; PATH-001 is only a lexical, provider-limited relation to the decoder. | `INV-002` | `DEC-001` | `AC-002` |
| `IMP-004` | `REQ-001` | regression | medium | detected | unknown | PATH-001 is lexical and the receipt frontier reports unavailable providers, so the absence of transitive references is not established. | `INV-001` | `DEC-001` | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove mobile profile.displayName decoding while retaining the configured one-release preservation window. | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | The request selects removal beginning at decodeDisplayName and explicitly supplies PRESERVE_RELEASES = 1 as the client compatibility treatment. |

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
| `REQ-001` | Remove support for the profile.displayName field from the mobile client, beginning with decodeDisplayName in mobile/ProfileDecoder.swift, while preserving compatibility for one release as configured by migrations/profile_field.py. Removal must eliminate the decoder behavior without leaving mobile references that still expect displayName. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | mobile/ProfileDecoder.swift no longer declares decodeDisplayName or a profile.displayName decoder field after implementation. | Verify the changed Swift source and a repository-wide symbol/string search. |
| `AC-002` | `REQ-001` | `IMP-003` | `INV-002` | The migration for profile.displayName continues to set PRESERVE_RELEASES to 1 through the removal transition. | Verify migrations/profile_field.py retains PRESERVE_RELEASES = 1 for FIELD = "profile.displayName". |
| `AC-003` | `REQ-001` | `IMP-004` | `INV-001` | No remaining mobile production or test code invokes decodeDisplayName or depends on profile.displayName, and the relevant mobile checks pass. | Use a repository-wide reference search and the project’s mobile build/test results after implementation. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Mobile profile decoding beginning at mobile/ProfileDecoder.swift:decodeDisplayName. | The file defines decodeDisplayName and reads payload["displayName"]. | High; directly verified in the repository. |
| Migration compatibility behavior for profile.displayName. | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and names profile.displayName. | High; directly verified and accepted by the request as compatibility treatment. |
| Transitive consumers, generated clients, and external payload producers. | The promoted scan found the migration-to-decoder path but reported provider fallback; a local search found no additional repository references. | Unknown beyond the direct files because graph providers were unavailable. |
| Graph paths for IMP-001 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Graph paths for IMP-002 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Graph paths for IMP-003 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Graph paths for IMP-004 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 1451adb626350224ac5fff9313ae5ee4; sha256 f2c90bb4b44ca7d8bc8487e8576d9c2849c083f161adf9e6484c30d532a4abf9; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | `AC-001`, `AC-002`, `AC-003` | Ready for planning. The requested client compatibility treatment is present as verified migration evidence; implementation must remove the decoder behavior and verify the detected functionality, data-contract, and regression impacts. |
