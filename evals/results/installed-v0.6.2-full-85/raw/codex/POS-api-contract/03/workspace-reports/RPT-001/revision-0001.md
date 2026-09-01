# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Profile API field name | The iOS client may fail to populate the user's display name. | iOS profile decoding and dependent user-facing views. | The API begins publishing profile.name while UserDTO still requests profile.displayName. | high | Choose either a one-release compatibility alias or a coordinated breaking update of the iOS decoder. | blocked |
| `IMP-002` | Persisted profile field key | Existing cached names may become unreadable or coexist with a second key, causing stale or missing values. | Profile cache reads, writes, and existing persisted entries. | New API responses use profile.name while cache code and stored data remain keyed by profile.displayName. | high | Define dual-read or migration behavior for the compatibility window, or coordinate an explicit cache migration with the rename. | blocked |
| `IMP-003` | Profile field deprecation lifecycle | Immediate removal may violate the repository's one-release deprecation policy, while documentation may advertise the wrong active or deprecated key. | API compatibility guarantees, release notes, and downstream migration timing. | profile.displayName is removed without defining the configured one-release transition. | medium | Select and document either a one-release alias period or an intentional breaking-release override. | blocked |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Rename profile.displayName to profile.name in api/profile.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Rename the published profile field from profile.displayName to profile.name, while explicitly selecting how the known iOS decoder, persisted cache key, changelog, and configured one-release deprecation window are handled. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The profile API currently publishes the field identifier profile.displayName. | verified | api/profile.py:1 defines PROFILE_FIELD = "profile.displayName". |
| `INV-002` | The iOS client currently decodes profile.displayName. | verified | ios/UserDTO.swift:1 defines decodedField = "profile.displayName". |
| `INV-003` | The profile cache currently persists data under profile.displayName. | verified | cache/profile_cache.py:1 defines CACHED_FIELD = "profile.displayName". |
| `INV-004` | Field deprecations are configured to remain supported for one release and the changelog currently identifies profile.displayName. | verified | docs/changelog.py:1-2 defines DEPRECATION_RELEASES = 1 and FIELD = "profile.displayName". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | api/profile.py:1 defines PROFILE_FIELD = "profile.displayName". |
| `INV-002` | `REQ-001` | `IMP-001` | ios/UserDTO.swift:1 defines decodedField = "profile.displayName". |
| `INV-003` | `REQ-001` | `IMP-002` | cache/profile_cache.py:1 defines CACHED_FIELD = "profile.displayName". |
| `INV-004` | `REQ-001` | `IMP-003` | docs/changelog.py:1-2 defines DEPRECATION_RELEASES = 1 and FIELD = "profile.displayName". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | interfaces | high | blocked | unknown | The files contain matching literal identifiers; the promoted receipt reports only lexical and structural inference because external graph providers were unavailable. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | data | high | blocked | unknown | The files contain matching literal identifiers; the promoted receipt reports only lexical and structural inference because external graph providers were unavailable. | `INV-001`, `INV-003` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | compatibility | medium | blocked | unknown | The changelog contains a one-release setting and the old identifier; the promoted receipt reports only lexical and structural inference because external graph providers were unavailable. | `INV-001`, `INV-004` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| How should the known consumers and the configured one-release deprecation window be handled? | One-release compatibility migration | `IMP-001`, `IMP-002`, `IMP-003` | Publish profile.name while retaining profile.displayName for one release, update iOS and cache behavior during that window, then remove the alias; this preserves compatibility but requires transitional code. |
| How should the known consumers and the configured one-release deprecation window be handled? | Coordinated immediate breaking rename | `IMP-001`, `IMP-002`, `IMP-003` | Rename the API, iOS decoder, cache key/migration behavior, and changelog together in one release and explicitly override the one-release window; this is simpler after release but breaks older clients and cached data unless separately migrated. |
| How should the known consumers and the configured one-release deprecation window be handled? | API-only immediate rename | `IMP-001`, `IMP-002`, `IMP-003` | Change only api/profile.py as narrowly requested; this is the smallest patch but knowingly leaves the iOS decoder, cache, and deprecation documentation inconsistent. |

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
| `REQ-001` | Rename the published profile field from profile.displayName to profile.name, while explicitly selecting how the known iOS decoder, persisted cache key, changelog, and configured one-release deprecation window are handled. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | After the change, the supported iOS client can decode a profile name from every supported API response during the selected migration window. | Verify the chosen API field set and the corresponding value in ios/UserDTO.swift with an automated or repository-level assertion. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | After the change, supported existing cached profile names remain readable and new names are written under the selected canonical key without ambiguous stale values. | Verify cache read/write or migration behavior against both an existing profile.displayName entry and a new profile.name entry as applicable. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-004` | The changelog and runtime behavior agree on the active key, legacy key, and removal timing for the configured one-release deprecation policy, or clearly record an intentional override. | Verify docs/changelog.py and the published API field behavior against the selected migration strategy. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The iOS compatibility behavior depends on the migration strategy. | none | API and iOS maintainers |
| `IMP-002` | blocked | The cache migration or compatibility behavior has not been selected. | none | API and cache maintainers |
| `IMP-003` | blocked | The request does not state whether to honor or override the configured one-release deprecation window. | none | API release owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Profile field publication in api/profile.py | Directly requested and verified at api/profile.py:1. | high |
| iOS profile decoding in ios/UserDTO.swift | Verified exact-key literal at ios/UserDTO.swift:1; receipt relationship PATH-001 remains provider-unverified. | medium |
| Persisted profile cache key in cache/profile_cache.py | Verified exact-key literal at cache/profile_cache.py:1; receipt relationship PATH-002 remains provider-unverified. | medium |
| Deprecation configuration and field documentation in docs/changelog.py | Verified DEPRECATION_RELEASES = 1 and the old identifier at docs/changelog.py:1-2; receipt relationship PATH-003 remains provider-unverified. | medium |
| Graph paths for IMP-001 | PATH-001: profile.displayName → profile.displayName | PATH-001: provider builtin; confidence lexical; location api/profile.py + ios/UserDTO.swift |
| Graph paths for IMP-002 | PATH-002: profile.displayName → profile.displayName | PATH-002: provider builtin; confidence lexical; location api/profile.py + cache/profile_cache.py |
| Graph paths for IMP-003 | PATH-003: profile.displayName → docs/changelog.py | PATH-003: provider builtin; confidence lexical; location api/profile.py + docs/changelog.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt 85aae53a61cc03a659a3768e7ca4e308; sha256 25af55f13ca808f433315380fbd1ea6cfd21dcb2d55455de4f4a2516fa17781c; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
