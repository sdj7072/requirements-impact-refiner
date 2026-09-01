# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | API profile-name field | The iOS decoder may no longer populate the user's name. | Existing and current iOS clients decoding profile.displayName | The API begins publishing only profile.name. | high | Coordinate decoder support for profile.name and, if compatibility is selected, retain or fall back to profile.displayName for the one-release window. | refining |
| `IMP-002` | Persisted profile-name cache key | Previously cached profile names may become unreadable or appear missing. | Users with cache entries written before the rename | Cache reads switch to profile.name without a legacy fallback or migration. | high | Read both keys during the compatibility window, prefer profile.name, and write or migrate to the new key. | refining |
| `IMP-003` | Profile field deprecation lifecycle | An immediate removal can contradict the configured one-release deprecation window or leave release documentation stale. | Older clients, cache data, and maintainers relying on changelog policy | profile.displayName is removed without documenting and supporting its one-release transition. | medium | Record profile.displayName as deprecated in favor of profile.name and align removal timing with DEPRECATION_RELEASES. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Rename profile.displayName to profile.name in api/profile.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Rename the profile field from profile.displayName to profile.name, with the migration scope and compatibility behavior explicitly selected for the API publisher, iOS decoder, persisted cache, and one-release deprecation record. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The iOS client continues to obtain a user's profile name from API responses during the field migration. | verified | api/profile.py publishes profile.displayName and ios/UserDTO.swift currently decodes exactly profile.displayName. |
| `INV-002` | Profiles persisted before the rename remain readable after deployment. | verified | cache/profile_cache.py currently persists the exact field profile.displayName. |
| `INV-003` | A deprecated profile field is retained or otherwise supported for the repository's configured one-release deprecation window. | verified | docs/changelog.py sets DEPRECATION_RELEASES = 1 and currently records FIELD = profile.displayName. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | api/profile.py publishes profile.displayName and ios/UserDTO.swift currently decodes exactly profile.displayName. |
| `INV-002` | `REQ-001` | `IMP-002` | cache/profile_cache.py currently persists the exact field profile.displayName. |
| `INV-003` | `REQ-001` | `IMP-003` | docs/changelog.py sets DEPRECATION_RELEASES = 1 and currently records FIELD = profile.displayName. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | interfaces | high | refining | unknown | The scan linked api/profile.py to ios/UserDTO.swift, but optional providers were unavailable; direct inspection shows both files use the old field string, while runtime decoder behavior remains unverified. | `INV-001` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | data | high | refining | unknown | The scan linked api/profile.py to cache/profile_cache.py, but optional providers were unavailable; direct inspection shows the cache persists the old field string, while runtime migration behavior remains unverified. | `INV-002` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | compatibility | medium | refining | unknown | The scan linked api/profile.py to docs/changelog.py, but optional providers were unavailable; direct inspection shows a one-release policy and the old field string, while release enforcement remains unverified. | `INV-003` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which compatibility scope should govern the profile field rename? | Use a one-release compatibility migration across API, iOS, cache, and changelog. | `IMP-001`, `IMP-002`, `IMP-003` | Preserves older clients and cached data and follows the stated deprecation policy, but temporarily supports both field names. |
| Which compatibility scope should govern the profile field rename? | Apply an atomic breaking rename across all four components now. | `IMP-001`, `IMP-002`, `IMP-003` | Leaves one canonical field immediately, but older iOS builds and existing cached records can break and the one-release policy must be explicitly overridden. |
| Which compatibility scope should govern the profile field rename? | Rename only api/profile.py as literally requested. | `IMP-001`, `IMP-002`, `IMP-003` | Minimizes the patch, but knowingly makes the publisher inconsistent with the decoder, cache, and deprecation record. |

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
| `REQ-001` | Rename the profile field from profile.displayName to profile.name, with the migration scope and compatibility behavior explicitly selected for the API publisher, iOS decoder, persisted cache, and one-release deprecation record. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | The selected migration leaves current iOS decoding functional when the API emits profile.name, with legacy support matching the selected compatibility scope. | Verify the emitted field set and decoder key or fallback behavior together. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | A value persisted under profile.displayName remains retrievable after the rename, and new persistence uses profile.name under the compatibility strategy selected. | Verify a pre-rename cache fixture and a post-rename write/read cycle. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | The changelog identifies profile.displayName as deprecated in favor of profile.name and its support/removal timing agrees with DEPRECATION_RELEASES, unless a breaking-policy override is explicitly selected. | Inspect docs/changelog.py and verify the selected release behavior. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| API field publisher | api/profile.py defines PROFILE_FIELD = profile.displayName. | verified |
| iOS API consumer | ios/UserDTO.swift defines decodedField = profile.displayName. | verified |
| Persisted cache | cache/profile_cache.py defines CACHED_FIELD = profile.displayName. | verified |
| Deprecation documentation | docs/changelog.py defines DEPRECATION_RELEASES = 1 and FIELD = profile.displayName. | verified |
| Graph paths for IMP-001 | PATH-001: profile.displayName → profile.displayName | PATH-001: provider builtin; confidence lexical; location api/profile.py + ios/UserDTO.swift |
| Graph paths for IMP-002 | PATH-002: profile.displayName → profile.displayName | PATH-002: provider builtin; confidence lexical; location api/profile.py + cache/profile_cache.py |
| Graph paths for IMP-003 | PATH-003: profile.displayName → docs/changelog.py | PATH-003: provider builtin; confidence lexical; location api/profile.py + docs/changelog.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt b8c8f74bbf95b251eae4fbf47e7bd12d; sha256 49fc80aadcd01aa1a3d59d864e9aaa10d1d1e300b1a7f9c9f09408d425c95ba0; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
