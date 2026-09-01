# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | 58c1f6048e2a14c8f8322f91425db8ee1ae06125964b53766ab7d476bd66892f | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Remove profile.displayName decoding and serialization support across mobile and desktop clients. | The desktop cache can continue writing profile.displayName after mobile decoding or field support is removed, producing incompatible cached profile data. | Mobile profile consumers and the desktop profile cache that directly serializes profile.displayName. | Removing profile.displayName support while desktop/ProfileCache.swift still serializes the field. | high | Stop desktop serialization of profile.displayName and verify the one-release preservation window before completing field removal. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove profile.displayName support beginning at decodeDisplayName in mobile/ProfileDecoder.swift, also eliminate direct serialization in desktop/ProfileCache.swift, and retain the configured one-release migration preservation until both clients no longer depend on the field. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The mobile profile decoder currently reads payload["displayName"] through decodeDisplayName for profile.displayName. | verified | mobile/ProfileDecoder.swift defines decodedField as profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | The profile.displayName migration is configured to preserve the field for one release. | verified | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |
| `INV-003` | The desktop profile cache currently serializes profile.displayName directly. | verified | desktop/ProfileCache.swift defines serializedField as "profile.displayName". |
| `INV-004` | Persisted canonical Markdown selected by current.json is the predecessor lineage; first.final.txt is chat output and is not canonical lineage bytes while a persisted report exists. | verified | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 58c1f6048e2a14c8f8322f91425db8ee1ae06125964b53766ab7d476bd66892f; first.final.txt was not used. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | mobile/ProfileDecoder.swift defines decodedField as profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-001` | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |
| `INV-003` | `REQ-001` | `IMP-001` | desktop/ProfileCache.swift defines serializedField as "profile.displayName". |
| `INV-004` | `REQ-001` | `IMP-001` | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 58c1f6048e2a14c8f8322f91425db8ee1ae06125964b53766ab7d476bd66892f; first.final.txt was not used. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | blocked | unknown | New current repository evidence shows desktop/ProfileCache.swift directly serializes profile.displayName. The one-release migration setting does not by itself demonstrate that this second client has stopped writing the field, so the earlier compatibility mitigation is reopened and removal is blocked pending desktop-client migration evidence. | `INV-001`, `INV-002`, `INV-003`, `INV-004` | `DEC-001` | `AC-001`, `AC-002` |

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
| blocked | `IMP-001` |
| superseded | none |
| reopened | none |
| new | none |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Remove support for profile.displayName beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while retaining the configured one-release migration preservation for existing clients. | `DEC-001` | none | Controller-created refinement revision. |
| `REQ-001` | Remove profile.displayName support beginning at decodeDisplayName in mobile/ProfileDecoder.swift, also eliminate direct serialization in desktop/ProfileCache.swift, and retain the configured one-release migration preservation until both clients no longer depend on the field. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | The configured one-release preservation window for profile.displayName has completed before the field is removed from either client. | Verify migrations/profile_field.py continues to identify profile.displayName with PRESERVE_RELEASES = 1 and provide release evidence that the preservation window completed. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-003` | desktop/ProfileCache.swift no longer serializes profile.displayName before profile field removal is completed. | Verify the direct profile.displayName serialization reference is absent from desktop/ProfileCache.swift and cover desktop cache serialization with a regression check. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | A second current client still serializes profile.displayName directly, so migration preservation alone cannot establish compatibility for removal. | `DEC-001` | Desktop client owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| mobile/ProfileDecoder.swift at decodeDisplayName | The file directly decodes profile.displayName. | verified |
| migrations/profile_field.py | The file names profile.displayName and configures one preserved release. | verified |
| desktop/ProfileCache.swift | The file directly serializes profile.displayName. | verified |
| Canonical predecessor lineage | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 58c1f6048e2a14c8f8322f91425db8ee1ae06125964b53766ab7d476bd66892f. | verified from the persisted current pointer and exact selected Markdown bytes; first.final.txt was not used as predecessor lineage |
| Graph paths for IMP-001 | PATH-001: profile.displayName → PRESERVE_RELEASES &#124;&#124; PATH-002: profile.displayName → decodeDisplayName | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt d5b4f9e797c71f8ceb1090846967256a; sha256 29fac876125ae99b6ae150b3e2c22015cd76df54f32f246c05ea97a7976c716f; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `DEC-001` | `IMP-001` | `AC-001`, `AC-002` | Not ready |
