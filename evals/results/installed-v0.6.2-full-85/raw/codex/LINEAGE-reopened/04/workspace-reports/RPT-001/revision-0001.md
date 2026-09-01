# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Remove mobile decoding of profile.displayName beginning at decodeDisplayName. | Older released clients could fail to obtain the display name if the producer stopped supplying the field before those clients aged out. | Released mobile clients that still call decodeDisplayName for profile.displayName. | Deploying the profile field removal without a compatibility overlap. | high | Retain profile.displayName for the configured one-release migration window while the new mobile release removes its decoder dependency. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove the mobile client's profile.displayName decoding path beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field through the configured one-release migration window so older client releases remain compatible during the transition. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The mobile profile decoder currently treats payload["displayName"] as an optional String and exposes it through decodeDisplayName. | verified | mobile/ProfileDecoder.swift defines decodedField as "profile.displayName" and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | The profile-field migration currently preserves profile.displayName for one release. | verified | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | mobile/ProfileDecoder.swift defines decodedField as "profile.displayName" and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-001` | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | accepted | unknown | Current source evidence verifies both endpoints: migrations/profile_field.py names profile.displayName and configures a one-release preservation window, and mobile/ProfileDecoder.swift is the current mobile consumer being removed. PATH-001 connects those files only lexically; the relationship remains coverage-limited because ast-grep, codegraph, and scip were unavailable. | `INV-001`, `INV-002` | `DEC-001` | `AC-001` |

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
| reopened | none |
| new | `IMP-001` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Remove the mobile client's profile.displayName decoding path beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field through the configured one-release migration window so older client releases remain compatible during the transition. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | The release that removes decodeDisplayName must overlap with one preserved release of profile.displayName, and the preservation must not be shortened below PRESERVE_RELEASES = 1 during that transition. | migrations/profile_field.py currently sets PRESERVE_RELEASES = 1 for FIELD = "profile.displayName"; mobile/ProfileDecoder.swift identifies decodeDisplayName as the client removal boundary. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| In scope: the mobile profile.displayName decode path beginning at mobile/ProfileDecoder.swift:decodeDisplayName. | The file directly defines decodeDisplayName and reads payload["displayName"]. | verified |
| In scope: the migration compatibility window for profile.displayName. | migrations/profile_field.py names the field and sets PRESERVE_RELEASES = 1. | verified |
| Out of scope: unrelated profile fields, non-mobile consumers, and upstream producer implementation details. | No supplied or scanned evidence identifies those consumers or implementations. | bounded unknown; no claim is made beyond the two verified files and their lexical path |
| Graph paths for IMP-001 | PATH-001: migrations/profile_field.py → mobile/ProfileDecoder.swift | PATH-001: provider builtin; confidence lexical; location migrations/profile_field.py + mobile/ProfileDecoder.swift |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 8d0b5117c533659e882aab0165c61d3e; sha256 cc6640dbf775f2bafe57b891ad9184b34b2ea38f93921e258f5563e370037061; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `DEC-001` | `IMP-001` | `AC-001` | Ready for planning. The selected compatibility resolution is the current one-release preservation setting; planning must retain that window while removing the mobile decoder path. |
