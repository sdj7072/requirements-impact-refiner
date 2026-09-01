# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | ab35988336df69c92b63c713bb6a909f040564acdc3d9ebe39d82d79f057b1ff | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | profile.displayName is removed while both mobile decoding and desktop cache serialization still reference it. | The desktop client may serialize or restore profile.displayName beyond the one-release window previously considered sufficient for mobile. | Released mobile clients and desktop clients using ProfileCache. | The field becomes unavailable before both clients and existing desktop caches have crossed a compatible release boundary. | high | Validate the preservation window against both client release cadences and the desktop cache lifecycle before completing removal. | detected |
| `IMP-002` | profile.displayName enters removal while a desktop cache serializes the same field. | Stored desktop cache entries may retain or require the field on a schedule different from server-side migration cleanup. | Profile records, payload serialization, and desktop ProfileCache entries. | Migration cleanup or cache reuse occurs without coordinating the one-release preservation boundary. | medium | Verify server retention and desktop cache migration or invalidation across the same release boundary. | mitigated |
| `IMP-003` | decodeDisplayName no longer supplies a display-name value while another client still serializes that field. | Mobile profile behavior may diverge from desktop cached-profile behavior or retain stale display-name assumptions. | Mobile consumers of ProfileDecoder.decodeDisplayName and cross-client profile behavior. | The mobile decoder is changed without validating behavior against payloads and caches that still contain or omit displayName. | medium | Test mobile decoding and cross-client profile behavior with both present and absent displayName values. | detected |
| `IMP-004` | Desktop cached profile state must transition away from serialized profile.displayName. | Existing cache entries or concurrent cache writes may reintroduce or expect the removed field after migration. | Desktop ProfileCache readers, writers, and persisted cache entries. | A cache created before removal is read or rewritten after the profile field contract changes. | medium | Define and verify cache versioning, invalidation, or tolerant deserialization for the transition. | detected |
| `IMP-005` | RPT-001 is revised while a chat transcript copy also contains profile.displayName text. | Using first.final.txt or normalized conversation text as predecessor bytes would break the report SHA lineage. | Persisted Requirements Impact Refiner report history. | Revision tooling hashes the chat response instead of the canonical Markdown selected by the persisted report pointer. | low | Use the persisted canonical artifact byte-for-byte and retain SHA-256 ab35988336df69c92b63c713bb6a909f040564acdc3d9ebe39d82d79f057b1ff as the predecessor. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove profile.displayName beginning at mobile/ProfileDecoder.swift decodeDisplayName, preserve it for one release through migrations/profile_field.py, and account for desktop/ProfileCache.swift serialization so both mobile decoding and desktop cached payloads remain compatible through the removal window. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The mobile profile decoder currently reads the displayName payload key and returns it as an optional string. | verified | mobile/ProfileDecoder.swift declares decodedField as profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | The profile.displayName migration preserves the field for one release during removal. | verified | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |
| `INV-003` | The desktop profile cache serializes profile.displayName directly. | verified | desktop/ProfileCache.swift declares serializedField = "profile.displayName". |
| `INV-004` | Persisted report lineage uses the exact canonical Markdown selected by current.json; first.final.txt is only a chat response unless no persisted report exists and it is complete canonical output. | verified | rir_previous recovered RPT-001 revision 1 from persisted lineage with SHA-256 ab35988336df69c92b63c713bb6a909f040564acdc3d9ebe39d82d79f057b1ff, consistent with the supplied continuity contract. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-003` | mobile/ProfileDecoder.swift declares decodedField as profile.displayName and decodeDisplayName returns payload["displayName"]. |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-004` | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |
| `INV-003` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | desktop/ProfileCache.swift declares serializedField = "profile.displayName". |
| `INV-004` | `REQ-001` | `IMP-005` | rir_previous recovered RPT-001 revision 1 from persisted lineage with SHA-256 ab35988336df69c92b63c713bb6a909f040564acdc3d9ebe39d82d79f057b1ff, consistent with the supplied continuity contract. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | detected | unknown | The one-release migration window was assessed against the mobile decoder, but desktop/ProfileCache.swift is now also known to serialize profile.displayName directly. The lexical graph cannot establish that one release covers both clients' release and cache lifecycles. | `INV-001`, `INV-002`, `INV-003` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | data | medium | mitigated | unknown | PRESERVE_RELEASES = 1 mitigates immediate field removal, but the desktop cache adds another serialized copy whose retention and cleanup timing are not established by the migration setting. | `INV-002`, `INV-003` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | regression | medium | detected | unknown | mobile/ProfileDecoder.swift remains the verified decoding point, and the graph now connects it lexically to the desktop serializer; downstream mobile behavior and regression coverage remain unverified. | `INV-001`, `INV-003` | `DEC-001` | `AC-003` |
| `IMP-004` | `REQ-001` | state/concurrency | medium | detected | unknown | desktop/ProfileCache.swift directly serializes profile.displayName, but no evidence establishes cache invalidation, schema versioning, or concurrent read/write behavior during field removal. | `INV-003`, `INV-002` | none | `AC-004` |
| `IMP-005` | `REQ-001` | regression | low | mitigated | unknown | The graph lexically associates first.final.txt with profile.displayName, but the supplied continuity contract and persisted lookup identify the canonical predecessor as the exact Markdown selected by current.json. | `INV-004` | none | `AC-005` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove profile.displayName from the mobile decoder with a one-release preservation window. | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | The request selects removal at decodeDisplayName, and migrations/profile_field.py supplies the one-release preservation mechanism for client compatibility. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | `IMP-001`, `IMP-002`, `IMP-003` |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | `IMP-004`, `IMP-005` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Remove the profile.displayName client field beginning at mobile/ProfileDecoder.swift decodeDisplayName, while preserving the field for one release through migrations/profile_field.py so older clients retain a compatibility window. | `DEC-001` | none | Controller-created refinement revision. |
| `REQ-001` | Remove profile.displayName beginning at mobile/ProfileDecoder.swift decodeDisplayName, preserve it for one release through migrations/profile_field.py, and account for desktop/ProfileCache.swift serialization so both mobile decoding and desktop cached payloads remain compatible through the removal window. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | profile.displayName remains available until both the released mobile decoder and desktop ProfileCache population have crossed a compatible release and cache boundary. | PRESERVE_RELEASES = 1 is verified, but desktop/ProfileCache.swift adds a second client whose release and cache lifecycle must be validated. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | Migration execution retains profile.displayName through the required client window and coordinates cleanup with desktop cache migration or invalidation. | Server-side one-release preservation and direct desktop serialization are verified; their cleanup ordering remains to be validated. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-001` | After removal, mobile decoding and cross-client profile behavior handle payloads with or without displayName without failure, divergence, or stale assumptions. | The mobile decoder and desktop serializer are verified reference points; downstream behavior and regression tests are not demonstrated. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-003` | Desktop cache entries created before, during, and after removal are read and rewritten safely without requiring or restoring profile.displayName. | desktop/ProfileCache.swift verifies direct serialization; cache versioning, invalidation, and transition tests are not supplied. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-004` | Revision 2 records the exact persisted revision-1 canonical Markdown SHA-256 without reconstructing or normalizing conversation text. | rir_previous recovered previous SHA-256 ab35988336df69c92b63c713bb6a909f040564acdc3d9ebe39d82d79f057b1ff from persisted RPT-001 lineage. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Mobile decoding boundary | mobile/ProfileDecoder.swift defines decodeDisplayName for profile.displayName. | High: directly verified in source. |
| Migration preservation boundary | migrations/profile_field.py sets PRESERVE_RELEASES = 1 for profile.displayName. | High for configuration; runtime release ordering is not demonstrated. |
| Desktop cache boundary | desktop/ProfileCache.swift declares serializedField = "profile.displayName". | High for direct serialization; cache lifecycle behavior is not demonstrated. |
| Cross-client compatibility and cache lifecycle | The receipt connects desktop/ProfileCache.swift lexically to the migration and mobile decoder, with one provider-limited frontier. | Unknown for end-to-end behavior because optional graph providers are unavailable. |
| Canonical report lineage | Persisted RPT-001 revision 1 supplies predecessor SHA-256 ab35988336df69c92b63c713bb6a909f040564acdc3d9ebe39d82d79f057b1ff; first.final.txt is treated only as a lexical conversation artifact. | High for persisted lineage identity; the PATH-003 relationship is lexical and not product evidence. |
| Graph paths for IMP-001 | PATH-001: profile.displayName → PRESERVE_RELEASES &#124;&#124; PATH-002: profile.displayName → decodeDisplayName | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Graph paths for IMP-002 | PATH-001: profile.displayName → PRESERVE_RELEASES | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py |
| Graph paths for IMP-003 | PATH-002: profile.displayName → decodeDisplayName | PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Graph paths for IMP-004 | PATH-001: profile.displayName → PRESERVE_RELEASES | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py |
| Graph paths for IMP-005 | PATH-003: profile.displayName → first.final.txt | PATH-003: provider builtin; confidence lexical; location desktop/ProfileCache.swift + first.final.txt |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt 79260d34a20c3e7fb40bcd44c6b54886; sha256 8c2c0801ff2e485b23214329b6d67e2f38ddde3028b464fdf490f4dd86933df2; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005` | Ready for planning with reopened client compatibility validation and explicit desktop cache migration or invalidation coverage. |
