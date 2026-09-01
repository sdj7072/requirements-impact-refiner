# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | 7b658c3296b7bd1991b248022092e6a3d177281573da9a28cdb822d538a78951 | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Remove profile.displayName consumption and serialization across mobile and desktop clients. | The desktop cache may continue writing or retaining profile.displayName after the server and mobile transition, producing stale cache data or a compatibility failure outside the original one-release assumption. | Desktop users with ProfileCache data, in addition to released mobile clients that still decode profile.displayName. | Removing or retiring profile.displayName while desktop/ProfileCache.swift still serializes the field or existing cache entries remain unmanaged. | high | Define and verify the desktop cache migration or serializer removal, including existing cached values, while retaining the one-release field-preservation window. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove profile.displayName only after coordinating both known clients: eliminate the mobile decode path beginning at decodeDisplayName, address desktop/ProfileCache.swift serialization and existing cached values, and retain the configured one-release migration window throughout the client transition. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The mobile profile decoder currently treats payload["displayName"] as an optional String and exposes it through decodeDisplayName. | verified | mobile/ProfileDecoder.swift defines decodedField as "profile.displayName" and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | The profile-field migration currently preserves profile.displayName for one release. | verified | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |
| `INV-003` | The desktop profile cache currently serializes profile.displayName directly. | verified | desktop/ProfileCache.swift defines serializedField = "profile.displayName". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | mobile/ProfileDecoder.swift defines decodedField as "profile.displayName" and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-001` | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |
| `INV-003` | `REQ-001` | `IMP-001` | desktop/ProfileCache.swift defines serializedField = "profile.displayName". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | blocked | unknown | New current source evidence identifies desktop/ProfileCache.swift as a second direct field consumer. PATH-001 connects the desktop cache to the one-release migration setting and PATH-002 connects it to the mobile decoder; both are lexical and provider-limited. PATH-003 also surfaces first.final.txt lexically, but persisted current.json identifies the canonical predecessor instead, so the transcript is covered only as an excluded artifact and does not support the application-impact conclusion. | `INV-001`, `INV-002`, `INV-003` | `DEC-001` | `AC-001`, `AC-002` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Treat the configured one-release preservation window as the compatibility resolution and remove the mobile decode path. | `REQ-001` | `IMP-001` | The request explicitly selects this resolution, and current repository evidence verifies PRESERVE_RELEASES = 1 for profile.displayName. |

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
| new | none |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Remove the mobile client's profile.displayName decoding path beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field through the configured one-release migration window so older client releases remain compatible during the transition. | `DEC-001` | none | Controller-created refinement revision. |
| `REQ-001` | Remove profile.displayName only after coordinating both known clients: eliminate the mobile decode path beginning at decodeDisplayName, address desktop/ProfileCache.swift serialization and existing cached values, and retain the configured one-release migration window throughout the client transition. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | The transition must retain profile.displayName for at least one release while every known client dependency is removed or migrated; PRESERVE_RELEASES must not be shortened below 1 during that overlap. | migrations/profile_field.py currently sets PRESERVE_RELEASES = 1, while mobile/ProfileDecoder.swift and desktop/ProfileCache.swift identify two current client dependencies. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-003` | Before profile.displayName is retired, desktop/ProfileCache.swift must stop serializing the field or apply an explicit cache migration, and regression coverage must verify that existing cached entries remain readable or are safely invalidated. | desktop/ProfileCache.swift currently defines serializedField = "profile.displayName"; no supplied evidence identifies serializer removal, cache migration, safe invalidation, or regression coverage. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The earlier one-release resolution covered the mobile decoder but new evidence identifies an unaddressed desktop serializer and gives no evidence for handling existing cached values. | `DEC-001` | Desktop client and profile migration owners |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| In scope: the mobile profile.displayName decode path beginning at mobile/ProfileDecoder.swift:decodeDisplayName. | The file directly defines decodeDisplayName and reads payload["displayName"]. | verified |
| In scope: the migration compatibility window for profile.displayName. | migrations/profile_field.py names the field and sets PRESERVE_RELEASES = 1. | verified |
| In scope: desktop profile cache serialization and existing cached profile.displayName values. | desktop/ProfileCache.swift directly defines serializedField = "profile.displayName"; behavior for existing cache entries is not supplied. | serializer verified; cache migration behavior unknown |
| Canonical predecessor lineage. | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 7b658c3296b7bd1991b248022092e6a3d177281573da9a28cdb822d538a78951, matching the hash of the exact selected Markdown file. | verified without reconstructing or normalizing predecessor bytes |
| first.final.txt is excluded as lineage evidence and as an application impact path. | It is the prior chat response; a persisted canonical RPT-001 report exists and current.json selects its Markdown artifact. PATH-003 is covered only to preserve the graph frontier. | verified by persisted report selection; the PATH-003 relationship itself is lexical |
| Out of scope: unrelated profile fields and unidentified consumers. | No supplied or traced evidence identifies other fields or consumers. | bounded unknown because optional graph providers were unavailable |
| Graph paths for IMP-001 | PATH-001: profile.displayName → profile.displayName &#124;&#124; PATH-002: profile.displayName → decodeDisplayName &#124;&#124; PATH-003: profile.displayName → first.final.txt | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift &#124;&#124; PATH-003: provider builtin; confidence lexical; location desktop/ProfileCache.swift + first.final.txt |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt 38b53c3309079fb067e2d987ad695cab; sha256 d650ddff37d48500e4e8ca47ee049cf402cbcd9644e1a7343497103ef1e9d21c; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `DEC-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
