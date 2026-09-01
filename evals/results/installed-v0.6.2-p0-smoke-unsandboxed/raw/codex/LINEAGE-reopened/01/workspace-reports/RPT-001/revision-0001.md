# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | profile.displayName is removed from mobile profile decoding. | A released client that still decodes displayName could receive payloads without the field before its compatibility window ends. | Mobile clients using ProfileDecoder.decodeDisplayName during the migration window. | Server-side removal of profile.displayName while a client release that expects it is still active. | high | Preserve profile.displayName for one release and verify release ordering before completing removal. | mitigated |
| `IMP-002` | The profile.displayName field enters a one-release removal migration. | Removing the stored or serialized field too early could discard data still needed by clients in the compatibility window. | Profile records and payload serialization for profile.displayName. | Migration cleanup runs before the configured preservation release has elapsed. | medium | Keep PRESERVE_RELEASES at 1 and verify cleanup occurs only after that release boundary. | mitigated |
| `IMP-003` | decodeDisplayName no longer supplies a display-name value from profile payloads. | Profile UI or client logic may continue to expect a decoded display name. | Potential mobile code paths downstream of ProfileDecoder.decodeDisplayName. | The decoder field is removed while a downstream caller still relies on its returned value. | medium | Remove or adapt downstream use and verify profile behavior with payloads that omit displayName. | detected |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove the profile.displayName client field beginning at mobile/ProfileDecoder.swift decodeDisplayName, while preserving the field for one release through migrations/profile_field.py so older clients retain a compatibility window. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The mobile profile decoder currently reads the displayName payload key and returns it as an optional string. | verified | mobile/ProfileDecoder.swift declares decodedField as profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | The profile.displayName migration preserves the field for one release during removal. | verified | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003` | mobile/ProfileDecoder.swift declares decodedField as profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002` | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | mitigated | unknown | Direct source evidence verifies the client consumption point and one-release preservation setting, while the promoted graph path remains lexical-only and cannot formally prove end-to-end compatibility. | `INV-001`, `INV-002` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | data | medium | mitigated | unknown | The migration file configures one-release preservation, while the fallback graph does not verify migration execution timing or post-window cleanup. | `INV-002` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | regression | medium | detected | unknown | The repository shows decodeDisplayName as the client consumption point, but the fallback graph could not verify downstream consumers and no supplied evidence demonstrates replacement presentation behavior or regression coverage. | `INV-001` | `DEC-001` | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove profile.displayName from the mobile decoder with a one-release preservation window. | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | The request selects removal at decodeDisplayName, and migrations/profile_field.py supplies the one-release preservation mechanism for client compatibility. |

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
| `REQ-001` | Remove the profile.displayName client field beginning at mobile/ProfileDecoder.swift decodeDisplayName, while preserving the field for one release through migrations/profile_field.py so older clients retain a compatibility window. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | The field remains available to the released client that still uses decodeDisplayName for one complete release before becoming unavailable. | migrations/profile_field.py currently sets PRESERVE_RELEASES = 1; release-order validation is still required to close the end-to-end impact. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | Migration execution retains profile.displayName data through the configured release boundary and removes it only afterward. | The configured preservation duration is verified; execution timing should be checked during implementation validation. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-001` | After removal, mobile profile decoding and its downstream consumers handle payloads without displayName without failure or stale display-name assumptions. | mobile/ProfileDecoder.swift is the verified starting point; downstream behavior and tests require implementation-time validation. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Client decoding boundary | mobile/ProfileDecoder.swift defines decodeDisplayName for profile.displayName. | High: directly verified in the named source file. |
| Migration compatibility boundary | migrations/profile_field.py sets PRESERVE_RELEASES = 1 for profile.displayName. | High: directly verified in the named migration file. |
| Downstream mobile consumers and post-window cleanup | No additional displayName references were found in the inspected repository beyond the decoder and migration evidence. | Medium: repository search is complete for textual references, but runtime behavior and tests are not demonstrated. |
| Graph paths for IMP-001 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Graph paths for IMP-002 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Graph paths for IMP-003 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 7057d50888782d584ecd3bcb13c1f557; sha256 f582197079e07f222ffa0ef983db630690a1f377f5141278c28559852cb7434a; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Ready for planning with implementation-time validation of release ordering, downstream decoder behavior, and migration timing. |
