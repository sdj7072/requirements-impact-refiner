# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Remove profile.displayName decoding beginning at the mobile profile decoder. | Already-released clients could lose display-name data or encounter incompatible cached/decoded profiles if the server field disappeared at the same time. | Mobile clients using decodeDisplayName and the detected desktop profile cache that names profile.displayName. | Deployment of decoder removal while older client versions or cached profile representations remain in use. | high | Preserve profile.displayName for one migration release and verify the detected client paths before the preservation window expires. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove mobile decoding support for the profile.displayName field, beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field through one migration release so already-released clients remain compatible during the transition. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Clients released before the decoder change continue to receive profile.displayName for the configured compatibility window. | verified | migrations/profile_field.py identifies FIELD as profile.displayName and sets PRESERVE_RELEASES to 1. |
| `INV-002` | Existing client code still names profile.displayName in mobile decoding and desktop serialization. | verified | mobile/ProfileDecoder.swift defines decodeDisplayName and desktop/ProfileCache.swift declares serializedField for profile.displayName. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | migrations/profile_field.py identifies FIELD as profile.displayName and sets PRESERVE_RELEASES to 1. |
| `INV-002` | `REQ-001` | `IMP-001` | mobile/ProfileDecoder.swift defines decodeDisplayName and desktop/ProfileCache.swift declares serializedField for profile.displayName. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | mitigated | unknown | Current source verifies that mobile/ProfileDecoder.swift decodes profile.displayName, desktop/ProfileCache.swift serializes the same field name, and migrations/profile_field.py preserves it for one release. The preservation window mitigates simultaneous field removal, but the promoted graph paths are lexical and provider-limited, so transitive compatibility cannot be marked fully verified. | `INV-001`, `INV-002` | `DEC-001` | `AC-001` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove the mobile decoder field while preserving profile.displayName for one release. | `REQ-001` | `IMP-001` | The request explicitly selects field removal, and the migration configuration supplies a one-release compatibility bridge for deployed clients. |

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
| `REQ-001` | Remove mobile decoding support for the profile.displayName field, beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field through one migration release so already-released clients remain compatible during the transition. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | When decodeDisplayName support is removed from mobile/ProfileDecoder.swift, profile.displayName remains available for one release, and the detected client references are verified or retired before that release window ends. | migrations/profile_field.py sets FIELD = "profile.displayName" and PRESERVE_RELEASES = 1; verification of the detected client references is required because graph coverage is provider-limited. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Mobile decoding of profile.displayName at decodeDisplayName in mobile/ProfileDecoder.swift. | The decoder declares decodedField = "profile.displayName" and returns payload["displayName"]. | Verified from the current repository source. |
| Compatibility migration for profile.displayName. | migrations/profile_field.py names the field and configures PRESERVE_RELEASES = 1. | Verified from the current repository source. |
| Detected desktop serialization and other transitive consumers. | desktop/ProfileCache.swift names profile.displayName, while the promoted scan reports an unknown frontier because optional graph providers were unavailable. | The direct desktop reference is verified, but its runtime relationship and any additional consumers remain unknown. |
| Graph paths for IMP-001 | PATH-001: profile.displayName → migrations/profile_field.py &#124;&#124; PATH-002: profile.displayName → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt b47105a9a9f4479a9a542d3d9a500b40; sha256 abdee382db17b11d3e790d4179e787ea558a98a7986e0efa9399c2ef4498f7a5; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `DEC-001` | `IMP-001` | `AC-001` | Ready for planning with the one-release compatibility mitigation recorded. Planning must include verification or retirement of detected client references before the preservation window expires. |
