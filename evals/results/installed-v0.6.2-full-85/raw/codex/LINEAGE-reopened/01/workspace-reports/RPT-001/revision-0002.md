# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | 33f45a1a03b75b715bfd06f4691dcdd0d027b48edca5c9b62e4dae0b508d7a8a | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | profile.displayName is removed from both mobile profile decoding and desktop profile-cache serialization. | The one-release plan may protect the mobile decoder while leaving the desktop client writing or retaining the removed field. | Mobile ProfileDecoder clients and desktop ProfileCache clients. | Field removal proceeds after considering only decodeDisplayName, while desktop/ProfileCache.swift still serializes profile.displayName. | high | Extend the compatibility boundary and removal work to the desktop serializer, then verify both clients across the preserved release. | refining |
| `IMP-002` | The desktop profile-cache schema stops serializing profile.displayName. | Existing cache entries or mixed-version desktop clients may retain, restore, or expect the removed field. | Desktop users whose profile data is persisted through ProfileCache. | The serializer changes without a verified cache migration or backward-compatible read strategy. | high | Define and test the desktop cache transition for old entries and mixed versions before removing the serialized field. | detected |
| `IMP-003` | The impact report advances from the persisted canonical predecessor. | Using first.final.txt could alter or normalize predecessor bytes and break report lineage. | Impact-report revision history and hash integrity. | A chat response is treated as canonical lineage despite an existing persisted report. | high | Read current.json and hash the exact Markdown file it selects; do not use or reconstruct first.final.txt. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove profile.displayName from both mobile decoding and desktop cache serialization only after the one-release preservation window, with an explicit desktop cache transition that prevents mixed-version clients from retaining or reintroducing the removed field. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The current mobile decoder reads profile.displayName through decodeDisplayName and tolerates a missing value as nil. | verified | mobile/ProfileDecoder.swift defines decodeDisplayName(payload:) -&gt; String? and returns payload["displayName"]. |
| `INV-002` | profile.displayName remains preserved for one release before removal. | verified | migrations/profile_field.py names FIELD = "profile.displayName" and sets PRESERVE_RELEASES = 1. |
| `INV-003` | The desktop profile cache serializes profile.displayName directly. | verified | desktop/ProfileCache.swift defines serializedField = "profile.displayName". |
| `INV-004` | Persisted current.json selects the exact canonical Markdown predecessor; first.final.txt is not lineage while that persisted report exists. | verified | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 33f45a1a03b75b715bfd06f4691dcdd0d027b48edca5c9b62e4dae0b508d7a8a, matching the exact file hash. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | mobile/ProfileDecoder.swift defines decodeDisplayName(payload:) -&gt; String? and returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002` | migrations/profile_field.py names FIELD = "profile.displayName" and sets PRESERVE_RELEASES = 1. |
| `INV-003` | `REQ-001` | `IMP-001`, `IMP-002` | desktop/ProfileCache.swift defines serializedField = "profile.displayName". |
| `INV-004` | `REQ-001` | `IMP-003` | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 33f45a1a03b75b715bfd06f4691dcdd0d027b48edca5c9b62e4dae0b508d7a8a, matching the exact file hash. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | refining | unknown | New direct source evidence identifies desktop/ProfileCache.swift as a second client of profile.displayName. The graph links the desktop serializer to both the migration and mobile decoder, but those receipt edges are lexical and a provider-unavailable frontier remains, so the prior client-compatibility acceptance is no longer sufficient as a complete compatibility conclusion. | `INV-001`, `INV-002`, `INV-003` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | data | high | detected | unknown | desktop/ProfileCache.swift directly names profile.displayName as its serialized field. The receipt connects that serializer to the migration through lexical PATH-001, but it does not verify cache read/write lifecycle behavior or mixed-version handling. | `INV-003`, `INV-002` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | regression | high | mitigated | unknown | The graph lexically links profile.displayName to first.final.txt, but the continuity evidence verifies that a persisted current.json exists and selects revision-0001.md with the matching canonical hash; first.final.txt is therefore excluded from predecessor bytes. | `INV-004` | none | `AC-003` |

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
| reopened | `IMP-001` |
| new | `IMP-002`, `IMP-003` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Remove profile.displayName support beginning at mobile/ProfileDecoder.swift's decodeDisplayName only after the one preserved release configured by migrations/profile_field.py. | `DEC-001` | none | Controller-created refinement revision. |
| `REQ-001` | Remove profile.displayName from both mobile decoding and desktop cache serialization only after the one-release preservation window, with an explicit desktop cache transition that prevents mixed-version clients from retaining or reintroducing the removed field. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | profile.displayName remains available for one release, and both mobile decodeDisplayName support and desktop ProfileCache serialization are removed or adapted only after that window. | The migration supplies the one-release boundary; current mobile and desktop source locations identify both client dependencies that must be covered. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | Desktop tests demonstrate that pre-removal cache entries remain readable or are safely invalidated, new cache entries omit profile.displayName, and mixed-version clients do not reintroduce it. | desktop/ProfileCache.swift currently serializes profile.displayName directly, while the graph frontier leaves cache lifecycle behavior unverified. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-004` | Revision 2 uses the exact bytes of the Markdown selected by RPT-001/current.json, whose SHA-256 matches current.json, and does not use first.final.txt. | The selected revision-0001.md hashes to 33f45a1a03b75b715bfd06f4691dcdd0d027b48edca5c9b62e4dae0b508d7a8a. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Persisted report lineage | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md, whose exact SHA-256 is 33f45a1a03b75b715bfd06f4691dcdd0d027b48edca5c9b62e4dae0b508d7a8a. | verified; first.final.txt was not used as predecessor lineage bytes |
| mobile/ProfileDecoder.swift at decodeDisplayName | decodeDisplayName reads payload["displayName"] and decodedField names profile.displayName. | verified |
| migrations/profile_field.py | FIELD is profile.displayName and PRESERVE_RELEASES is 1. | verified |
| desktop/ProfileCache.swift | serializedField is set directly to profile.displayName. | verified |
| Transitive repository coverage | PATH-001 links desktop/ProfileCache.swift to migrations/profile_field.py and PATH-002 links desktop/ProfileCache.swift to mobile/ProfileDecoder.swift; both edges are lexical, and provider coverage ends at FRONTIER-001. | unknown beyond the directly inspected sources |
| Non-canonical chat artifact | PATH-003 points to first.final.txt, which is a chat response rather than canonical lineage because a persisted report exists. | excluded from lineage; graph confidence remains lexical |
| Graph paths for IMP-001 | PATH-001: profile.displayName → PRESERVE_RELEASES &#124;&#124; PATH-002: profile.displayName → decodeDisplayName | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Graph paths for IMP-002 | PATH-001: profile.displayName → PRESERVE_RELEASES | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py |
| Graph paths for IMP-003 | PATH-003: profile.displayName → first.final.txt | PATH-003: provider builtin; confidence lexical; location desktop/ProfileCache.swift + first.final.txt |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt 3d642786d89a9dc8cc57e3145b7c2f01; sha256 825c1dd21429fa979e6f3a6483c2f6b546de79bc99caaa488cab348871c7d8f8; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready for implementation planning: IMP-001 is reopened by the second client and IMP-002 requires a desktop cache transition. Reassess the one-release rollout across both clients and close AC-001 and AC-002 first; canonical lineage handling is mitigated by AC-003. |
