# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Remove profile.displayName decoding beginning at the mobile profile decoder. | Already-released clients could lose display-name data if the field disappears at the same time as decoder removal. | Mobile clients using decodeDisplayName and the profile.displayName payload contract. | Deploying decoder removal while an older client release still consumes profile.displayName. | high | Preserve profile.displayName for one migration release and retire the decoder dependency after the preservation window. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove mobile decoding support for profile.displayName, beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field for one migration release so already-released clients remain compatible during the transition. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Clients released before the decoder change continue to receive profile.displayName for the configured compatibility window. | verified | migrations/profile_field.py identifies FIELD as profile.displayName and sets PRESERVE_RELEASES to 1. |
| `INV-002` | Existing mobile client code still decodes profile.displayName through decodeDisplayName. | verified | mobile/ProfileDecoder.swift sets decodedField to profile.displayName and decodeDisplayName returns payload["displayName"]. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | migrations/profile_field.py identifies FIELD as profile.displayName and sets PRESERVE_RELEASES to 1. |
| `INV-002` | `REQ-001` | `IMP-001` | mobile/ProfileDecoder.swift sets decodedField to profile.displayName and decodeDisplayName returns payload["displayName"]. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | mitigated | unknown | Current source verifies that mobile/ProfileDecoder.swift decodes profile.displayName and migrations/profile_field.py preserves the same field for one release. The supplied evidence supports the compatibility resolution, but the promoted relationship path is lexical and provider-limited, so transitive compatibility remains recorded as mitigated rather than fully verified. | `INV-001`, `INV-002` | `DEC-001` | `AC-001` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove profile.displayName decoding while preserving the field for one release. | `REQ-001` | `IMP-001` | The request selects decoder-side field removal, and PRESERVE_RELEASES = 1 supplies the compatibility bridge for deployed clients. |

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
| `REQ-001` | Remove mobile decoding support for profile.displayName, beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field for one migration release so already-released clients remain compatible during the transition. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | When decodeDisplayName support is removed from mobile/ProfileDecoder.swift, profile.displayName remains available for exactly one release, and the mobile decoder dependency is retired by the end of that window. | migrations/profile_field.py sets FIELD = "profile.displayName" and PRESERVE_RELEASES = 1; mobile/ProfileDecoder.swift identifies the decoder dependency to retire. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Mobile decoding of profile.displayName at decodeDisplayName in mobile/ProfileDecoder.swift | The decoder declares decodedField = "profile.displayName" and returns payload["displayName"]. | Verified from current repository source. |
| Compatibility migration for profile.displayName | migrations/profile_field.py names the field and configures PRESERVE_RELEASES = 1. | Verified from current repository source. |
| Other transitive profile consumers or producers | The promoted scan reports a provider-unavailable frontier and only a lexical path between the supplied migration and decoder locations. | Limited; no additional consumers or producers were established. |
| Graph paths for IMP-001 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt c800d1aeaa6cf369bf87a650bc993826; sha256 a02ebcedb8e32064388050a1d730500d5494a0d212e39dbe8b3e2e08200a149c; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `DEC-001` | `IMP-001` | `AC-001` | Ready for planning with the one-release compatibility mitigation recorded. Planning must coordinate decoder removal with the preservation window and verify the mobile dependency is retired before the window expires. |
