# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Remove mobile decoding of profile.displayName at decodeDisplayName. | Clients still expecting displayName could fail to read the profile field when decoder support is removed. | Mobile profile clients that consume profile.displayName. | Removal of decodeDisplayName support for profile.displayName. | high | Retain the configured one-release preservation window and verify that the window has been honored before treating compatibility as fully resolved. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove support for profile.displayName beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while retaining the configured one-release migration preservation for existing clients. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The mobile profile decoder currently reads payload["displayName"] through decodeDisplayName for profile.displayName. | verified | mobile/ProfileDecoder.swift lines 1-3 define decodedField as profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | The profile.displayName migration is configured to preserve the field for one release. | verified | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | mobile/ProfileDecoder.swift lines 1-3 define decodedField as profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-001` | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | mitigated | unknown | The supplied current sources name the same profile.displayName field and set PRESERVE_RELEASES to 1. This directly documents the intended compatibility mitigation, while the graph receipt remains lexical because optional providers were unavailable. | `INV-001`, `INV-002` | `DEC-001` | `AC-001` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove profile.displayName decoding with one preserved release. | `REQ-001` | `IMP-001` | The request selects removal at decodeDisplayName, and the supplied migration evidence establishes PRESERVE_RELEASES = 1 for the same field. |

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
| `REQ-001` | Remove support for profile.displayName beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while retaining the configured one-release migration preservation for existing clients. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | The removal retains the configured one-release preservation window for profile.displayName; compatibility is resolved once the preserved release is verified as completed and decoding support is removed. | Verify migrations/profile_field.py still identifies profile.displayName with PRESERVE_RELEASES = 1, confirm the preserved release has completed, and verify mobile/ProfileDecoder.swift no longer decodes the field. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| mobile/ProfileDecoder.swift at decodeDisplayName | The file directly defines decoding for profile.displayName. | verified |
| migrations/profile_field.py | The file directly names profile.displayName and sets PRESERVE_RELEASES to 1. | verified |
| Graph paths for IMP-001 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 4bf80da049b9383cdf1392d0d6974955; sha256 59a95241b9a2aa323664245405f491de7cb039bcc9aa354dbfa66edd13db6b24; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `DEC-001` | `IMP-001` | `AC-001` | Ready for planning with a remaining compatibility verification: confirm the configured preserved release has completed before marking the client compatibility impact resolved. |
