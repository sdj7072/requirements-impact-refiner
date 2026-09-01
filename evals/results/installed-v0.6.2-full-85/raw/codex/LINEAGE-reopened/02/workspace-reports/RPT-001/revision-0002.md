# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | 9c3cd81c8d69d21b8a88a0f6051393602b84e3353e79a3ae6d95a884cae0cc11 | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Mobile profile display-name decoding is removed. | The client could continue exposing or expecting displayName if the decoder symbol or field constant remains. | The mobile profile decoding path beginning at decodeDisplayName. | Building or running the mobile client after profile.displayName support is removed. | medium | Remove decodeDisplayName and the associated profile.displayName decoder declaration, then verify no mobile reference remains. | detected |
| `IMP-002` | The profile data contract stops decoding or serializing profile.displayName across mobile and desktop clients. | Removing only the mobile decoder leaves the desktop client writing the retired field and preserves an inconsistent profile contract. | Mobile profile payload handling and desktop profile cache records. | Profile data is decoded on mobile or serialized by the desktop cache during the removal transition. | high | Remove both client uses, retain the migration window, and verify repository-wide profile.displayName references after implementation. | detected |
| `IMP-003` | profile.displayName is retired across mobile decoding and desktop cache serialization. | The prior compatibility treatment covered the migration window but did not account for the desktop client continuing to serialize the field. | Mobile and desktop client versions spanning the field-removal release, including existing desktop cache records. | A desktop client writes or reads cached profiles while profile.displayName is being removed. | high | Reopen compatibility validation until the desktop serializer is removed and cross-version cache behavior passes within the one-release preservation window. | detected |
| `IMP-004` | Removal of profile.displayName references from all client code. | A stale decoder, serializer, or fixture could preserve the retired behavior or cause build/runtime regressions. | Mobile and desktop code and tests that decode, serialize, or cache profile.displayName. | Compiling, testing, or loading cached profiles after field removal. | medium | Search all client production and test code for decodeDisplayName/profile.displayName and run both client verification suites. | detected |
| `IMP-005` | Desktop cached profile state no longer serializes profile.displayName. | Existing or concurrently written cache entries may retain the retired field or become incompatible with updated readers. | Desktop users with profile cache records created before or during the transition. | Reading or writing desktop profile cache data across the field-removal release. | medium | Remove the serializer and verify old/new cache read-write behavior across the configured one-release window. | detected |
| `IMP-006` | The impact-report revision continues from persisted canonical Markdown. | Using first.final.txt as predecessor bytes could create a false report lineage or normalize content that was never canonical. | RPT-001 revision history and delta integrity. | Selecting predecessor bytes for this report revision. | medium | Use current.json to select revision-0001.md, verify its exact hash, and exclude first.final.txt from lineage. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove profile.displayName from every client boundary now evidenced in the repository: remove decoding beginning at mobile/ProfileDecoder.swift:decodeDisplayName and remove direct serialization in desktop/ProfileCache.swift. Retain the one-release migration window, and verify both mobile payload handling and desktop cache compatibility before considering the client compatibility impact closed. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The current mobile profile decoder reads the displayName payload key and returns it as an optional string. | verified | mobile/ProfileDecoder.swift declares profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | The profile-field migration preserves compatibility for one release. | verified | migrations/profile_field.py sets PRESERVE_RELEASES = 1 for FIELD = "profile.displayName". |
| `INV-003` | The desktop profile cache currently serializes profile.displayName directly. | verified | desktop/ProfileCache.swift declares serializedField = "profile.displayName". |
| `INV-004` | The persisted RPT-001 selector identifies revision-0001.md as the canonical predecessor; the chat response file is not canonical lineage. | verified | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 9c3cd81c8d69d21b8a88a0f6051393602b84e3353e79a3ae6d95a884cae0cc11, matching the exact file hash. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | mobile/ProfileDecoder.swift declares profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-003`, `IMP-005` | migrations/profile_field.py sets PRESERVE_RELEASES = 1 for FIELD = "profile.displayName". |
| `INV-003` | `REQ-001` | `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005` | desktop/ProfileCache.swift declares serializedField = "profile.displayName". |
| `INV-004` | `REQ-001` | `IMP-006` | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 9c3cd81c8d69d21b8a88a0f6051393602b84e3353e79a3ae6d95a884cae0cc11, matching the exact file hash. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | medium | detected | unknown | PATH-002 lexically connects the newly evidenced desktop serializer to mobile/ProfileDecoder.swift; provider-limited coverage does not verify all callers. | `INV-001` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | data | high | detected | unknown | PATH-001 and PATH-002 show lexical relations from desktop/ProfileCache.swift to the migration and mobile decoder, establishing a broader client data-contract surface with provider-limited confidence. | `INV-001`, `INV-002`, `INV-003` | `DEC-001` | `AC-001`, `AC-002`, `AC-004` |
| `IMP-003` | `REQ-001` | compatibility | high | detected | unknown | The verified one-release migration remains present, but PATH-001 and PATH-002 expose a second client boundary that serializes the field directly; lexical graph confidence prevents treating compatibility as closed. | `INV-002`, `INV-003`, `INV-001` | `DEC-001` | `AC-002`, `AC-004`, `AC-005` |
| `IMP-004` | `REQ-001` | regression | medium | detected | unknown | PATH-001 connects the desktop serializer to the migration with lexical confidence, and the provider frontier means additional stale references are not ruled out. | `INV-001`, `INV-003` | `DEC-001` | `AC-003`, `AC-004` |
| `IMP-005` | `REQ-001` | state/concurrency | medium | detected | unknown | PATH-001 identifies desktop/ProfileCache.swift as a cache boundary related lexically to the one-release migration; cache lifetime and read/write behavior remain outside verified graph coverage. | `INV-003`, `INV-002` | none | `AC-004`, `AC-005` |
| `IMP-006` | `REQ-001` | operations | medium | mitigated | unknown | PATH-003 lexically associates desktop/ProfileCache.swift with first.final.txt, but current.json and the exact canonical Markdown hash establish that first.final.txt is only chat output and is excluded from predecessor lineage. | `INV-004` | none | `AC-006` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove mobile profile.displayName decoding while retaining the configured one-release preservation window. | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | The request selects removal beginning at decodeDisplayName and explicitly supplies PRESERVE_RELEASES = 1 as the client compatibility treatment. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | `IMP-005`, `IMP-006` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Remove support for the profile.displayName field from the mobile client, beginning with decodeDisplayName in mobile/ProfileDecoder.swift, while preserving compatibility for one release as configured by migrations/profile_field.py. Removal must eliminate the decoder behavior without leaving mobile references that still expect displayName. | `DEC-001` | none | Controller-created refinement revision. |
| `REQ-001` | Remove profile.displayName from every client boundary now evidenced in the repository: remove decoding beginning at mobile/ProfileDecoder.swift:decodeDisplayName and remove direct serialization in desktop/ProfileCache.swift. Retain the one-release migration window, and verify both mobile payload handling and desktop cache compatibility before considering the client compatibility impact closed. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | mobile/ProfileDecoder.swift no longer declares decodeDisplayName or a profile.displayName decoder field after implementation. | Verify the changed Swift source and a repository-wide symbol/string search. |
| `AC-002` | `REQ-001` | `IMP-003` | `INV-002` | The migration for profile.displayName continues to set PRESERVE_RELEASES to 1 through the removal transition. | Verify migrations/profile_field.py retains PRESERVE_RELEASES = 1 for FIELD = "profile.displayName". |
| `AC-003` | `REQ-001` | `IMP-004` | `INV-001` | No remaining mobile or desktop production or test code invokes decodeDisplayName, serializes, or otherwise depends on profile.displayName, and both relevant client checks pass. | Use a repository-wide reference search and mobile and desktop build/test results after implementation. |
| `AC-004` | `REQ-001` | `IMP-005` | `INV-003` | desktop/ProfileCache.swift no longer serializes profile.displayName after implementation. | Verify the changed desktop source and repository-wide profile.displayName references. |
| `AC-005` | `REQ-001` | `IMP-003` | `INV-002` | Compatibility checks cover mobile decoding and desktop cache records across the one-release preservation window, including data written before removal. | Verify cross-version mobile payload and desktop cache read/write test results for the removal transition. |
| `AC-006` | `REQ-001` | `IMP-006` | `INV-004` | The new RPT-001 revision records revision-0001.md SHA-256 9c3cd81c8d69d21b8a88a0f6051393602b84e3353e79a3ae6d95a884cae0cc11 as its predecessor without using or normalizing first.final.txt. | Verify the new report state previous_sha256 and RPT-001 selector chain after publication. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Canonical predecessor for RPT-001. | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md and its exact SHA-256 is 9c3cd81c8d69d21b8a88a0f6051393602b84e3353e79a3ae6d95a884cae0cc11. | High; selector metadata and exact file hash agree. first.final.txt is excluded from lineage. |
| Mobile profile decoding beginning at mobile/ProfileDecoder.swift:decodeDisplayName. | The file defines decodeDisplayName and reads payload["displayName"]. | High for the direct current behavior; transitive relations remain lexical. |
| Desktop profile cache serialization in desktop/ProfileCache.swift. | The file declares serializedField = "profile.displayName". | High for the direct current behavior; cache lifetime and compatibility behavior are not otherwise evidenced. |
| Migration compatibility behavior for profile.displayName. | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and names profile.displayName. | High for the configured window, but insufficient to close multi-client compatibility after discovering the desktop serializer. |
| Additional transitive consumers, generated clients, cache readers, and external payload producers. | The trace found desktop-to-migration and desktop-to-mobile paths, but optional graph providers were unavailable. | Unknown beyond the directly inspected files. |
| Graph paths for IMP-001 | PATH-002: profile.displayName → decodeDisplayName | PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Graph paths for IMP-002 | PATH-001: profile.displayName → PRESERVE_RELEASES &#124;&#124; PATH-002: profile.displayName → decodeDisplayName | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Graph paths for IMP-003 | PATH-001: profile.displayName → PRESERVE_RELEASES &#124;&#124; PATH-002: profile.displayName → decodeDisplayName | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Graph paths for IMP-004 | PATH-001: profile.displayName → PRESERVE_RELEASES | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py |
| Graph paths for IMP-005 | PATH-001: profile.displayName → PRESERVE_RELEASES | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py |
| Graph paths for IMP-006 | PATH-003: profile.displayName → first.final.txt | PATH-003: provider builtin; confidence lexical; location desktop/ProfileCache.swift + first.final.txt |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt 247de63d7df500fd7dd11482cb20c8a7; sha256 32cff1dda84403206e8999ff9119ca7c6578d2e7db007541fe83580d14d98d25; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006` | Ready for planning with compatibility reopened. The one-release migration treatment remains verified, but IMP-003 cannot be considered resolved until desktop serialization is removed and cross-client transition checks pass. |
