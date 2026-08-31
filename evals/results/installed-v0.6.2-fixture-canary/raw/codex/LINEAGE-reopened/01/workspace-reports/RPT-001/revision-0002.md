# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | e3ee34c54184eeff433ccca148f8ff8823079b3392876d9aac9203e7be4ea255 | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Remove profile.displayName decoding beginning at the mobile profile decoder while accounting for the desktop serializer. | A desktop client can continue serializing profile.displayName after mobile decoding support changes, leaving incompatible cached or transferred profile data when the preservation window ends. | Mobile clients using decodeDisplayName and desktop clients using ProfileCache serializedField for profile.displayName. | Removal or expiry of profile.displayName while either detected client path still reads, writes, or stores the field. | high | Preserve the field for one release and verify or retire both the mobile decoder and desktop serializer before that release window expires. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove mobile decoding support for the profile.displayName field, beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field through one migration release and verifying or retiring every detected client serializer, including desktop/ProfileCache.swift, before the preservation window ends. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Clients released before the decoder change continue to receive profile.displayName for the configured compatibility window. | verified | migrations/profile_field.py identifies FIELD as profile.displayName and sets PRESERVE_RELEASES to 1. |
| `INV-002` | Existing client code names profile.displayName in mobile decoding and desktop serialization. | verified | mobile/ProfileDecoder.swift defines decodeDisplayName for profile.displayName, and desktop/ProfileCache.swift directly declares serializedField = "profile.displayName". |
| `INV-003` | Persisted report lineage is selected by RPT-001/current.json and its exact canonical Markdown hash; first.final.txt is not canonical predecessor bytes. | verified | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 e3ee34c54184eeff433ccca148f8ff8823079b3392876d9aac9203e7be4ea255, which matches the exact file hash. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | migrations/profile_field.py identifies FIELD as profile.displayName and sets PRESERVE_RELEASES to 1. |
| `INV-002` | `REQ-001` | `IMP-001` | mobile/ProfileDecoder.swift defines decodeDisplayName for profile.displayName, and desktop/ProfileCache.swift directly declares serializedField = "profile.displayName". |
| `INV-003` | `REQ-001` | `IMP-001` | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 e3ee34c54184eeff433ccca148f8ff8823079b3392876d9aac9203e7be4ea255, which matches the exact file hash. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | mitigated | unknown | The one-release migration window mitigates simultaneous removal, but desktop/ProfileCache.swift directly serializes profile.displayName in addition to the mobile decoder. The canonical predecessor already recorded this desktop dependency and classified IMP-001 as mitigated, so the new evidence corroborates rather than resolves or reopens the risk. Runtime/transitive coverage remains provider-limited. | `INV-001`, `INV-002`, `INV-003` | `DEC-001` | `AC-001` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove the mobile decoder field while preserving profile.displayName for one release. | `REQ-001` | `IMP-001` | The request explicitly selects field removal, and the migration configuration supplies a one-release compatibility bridge for deployed clients. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | `IMP-001` |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | none |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Remove mobile decoding support for the profile.displayName field, beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field through one migration release so already-released clients remain compatible during the transition. | `DEC-001` | none | Controller-created refinement revision. |
| `REQ-001` | Remove mobile decoding support for the profile.displayName field, beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field through one migration release and verifying or retiring every detected client serializer, including desktop/ProfileCache.swift, before the preservation window ends. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Before the one-release profile.displayName preservation window expires, decodeDisplayName in mobile/ProfileDecoder.swift and the direct serializer in desktop/ProfileCache.swift are each verified compatible with field removal or retired, and no supported client still requires the field. | Current evidence verifies PRESERVE_RELEASES = 1 and the direct desktop serializedField reference; completion requires client-path verification because graph coverage remains lexical and provider-limited. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Canonical predecessor lineage. | RPT-001/current.json selects revision-0001.md, and the selected file's exact SHA-256 matches e3ee34c54184eeff433ccca148f8ff8823079b3392876d9aac9203e7be4ea255. | Verified from persisted report metadata and exact canonical Markdown bytes; first.final.txt was excluded from lineage. |
| Mobile decoding and desktop serialization of profile.displayName. | mobile/ProfileDecoder.swift defines decodeDisplayName, and desktop/ProfileCache.swift directly serializes profile.displayName. | Both direct source references are verified; their runtime interaction remains unverified. |
| Compatibility migration window. | migrations/profile_field.py sets FIELD = "profile.displayName" and PRESERVE_RELEASES = 1. | Verified current configuration, but one release does not by itself prove every client is migrated. |
| Transitive client consumers. | The promoted scan exposes lexical paths from desktop/ProfileCache.swift to the migration and mobile decoder plus a provider-unavailable frontier. | The selected relationships remain unknown at runtime because optional graph providers were unavailable. |
| Chat-response artifact first.final.txt. | The scan detected first.final.txt lexically, but persisted current.json selects revision-0001.md as canonical lineage. | Excluded from compatibility evidence and predecessor hashing; it is not a repository behavior source. |
| Graph paths for IMP-001 | PATH-001: profile.displayName → profile.displayName &#124;&#124; PATH-002: profile.displayName → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt e18a4c72c1cae624114d91b0f64d3509; sha256 690a768f573af9384191ac69e9f68631501333fe11ae6cbfa607ad6f27a2d71e; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `DEC-001` | `IMP-001` | `AC-001` | Ready for planning with IMP-001 unchanged as mitigated. Planning must verify or retire both detected client paths before the one-release preservation window expires; full compatibility resolution is not yet evidenced. |
