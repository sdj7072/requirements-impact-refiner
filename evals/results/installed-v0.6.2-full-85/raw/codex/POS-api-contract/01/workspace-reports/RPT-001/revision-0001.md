# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | The API field becomes profile.name. | Existing iOS builds can no longer decode the user's display name if the old field disappears immediately. | Released iOS clients and any staged rollout in which server and app versions differ. | A response contains only profile.name while the client still requests profile.displayName. | high | Choose either a one-release alias/fallback rollout or a coordinated breaking update of producer and client. | detected |
| `IMP-002` | The canonical persisted profile key becomes profile.name. | Existing cached records may be unreadable or may continue reintroducing the deprecated key. | Users with cache entries written before the rename and code paths reading cached profiles. | New code reads only profile.name from an entry stored with profile.displayName, or keeps writing the legacy key. | high | Define read-old/write-new migration behavior for one release, or invalidate/migrate all cache entries during a coordinated breaking rollout. | detected |
| `IMP-003` | profile.displayName becomes deprecated in favor of profile.name. | The implementation may either remove the old field too early or leave the changelog/policy record inconsistent with the actual rollout. | Release coordination, maintainers, and downstream consumers relying on the stated compatibility window. | The API rename ships without updating the deprecation record and removal timing. | medium | Record the replacement and apply the configured one-release compatibility window, unless an explicit breaking rollout is selected. | detected |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Rename profile.displayName to profile.name in api/profile.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Rename the published profile field from profile.displayName to profile.name, while explicitly choosing and implementing a rollout strategy for the iOS decoder and persisted cache under the repository's one-release deprecation policy. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The profile API currently publishes the field as profile.displayName. | verified | api/profile.py:1 defines PROFILE_FIELD = "profile.displayName". |
| `INV-002` | The iOS client currently decodes the profile name from profile.displayName. | verified | ios/UserDTO.swift:1 defines decodedField = "profile.displayName". |
| `INV-003` | Persisted profile cache entries currently use profile.displayName. | verified | cache/profile_cache.py:1 defines CACHED_FIELD = "profile.displayName". |
| `INV-004` | Deprecated fields are retained for one release. | verified | docs/changelog.py:1 defines DEPRECATION_RELEASES = 1; line 2 still names profile.displayName. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | api/profile.py:1 defines PROFILE_FIELD = "profile.displayName". |
| `INV-002` | `REQ-001` | `IMP-001` | ios/UserDTO.swift:1 defines decodedField = "profile.displayName". |
| `INV-003` | `REQ-001` | `IMP-002` | cache/profile_cache.py:1 defines CACHED_FIELD = "profile.displayName". |
| `INV-004` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | docs/changelog.py:1 defines DEPRECATION_RELEASES = 1; line 2 still names profile.displayName. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | interfaces | high | detected | unknown | The endpoint strings are verified in api/profile.py and ios/UserDTO.swift, but the promoted scan only weakly infers their dependency via PATH-001 and reports unavailable optional providers. | `INV-001`, `INV-002`, `INV-004` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | data | high | detected | unknown | The endpoint strings are verified in api/profile.py and cache/profile_cache.py, but the promoted scan only weakly infers their dependency via PATH-002 and reports unavailable optional providers. | `INV-001`, `INV-003`, `INV-004` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | compatibility | medium | detected | unknown | The deprecation constants are verified in docs/changelog.py, but the promoted scan only weakly infers their relationship to the API rename via PATH-003 and reports unavailable optional providers. | `INV-001`, `INV-004` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Should the rename honor the configured one-release deprecation window, or be an immediate coordinated breaking change? | One-release compatibility rollout | `IMP-001`, `IMP-002`, `IMP-003` | Temporarily support profile.displayName alongside profile.name; update iOS to prefer the new key with old-key fallback, migrate cache reads/writes, then remove the alias after one release. |
| Should the rename honor the configured one-release deprecation window, or be an immediate coordinated breaking change? | Immediate coordinated rename | `IMP-001`, `IMP-002`, `IMP-003` | Update API, iOS decoder, cache format/migration, and changelog together now; simpler end state, but incompatible with already-released clients and old cached data unless deployments and invalidation are tightly coordinated. |

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
| `REQ-001` | Rename the published profile field from profile.displayName to profile.name, while explicitly choosing and implementing a rollout strategy for the iOS decoder and persisted cache under the repository's one-release deprecation policy. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | The selected rollout must specify how iOS decodes profile.name and what happens when it receives only the legacy or only the new field. | Current iOS code recognizes only profile.displayName. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | The selected rollout must specify reads of existing profile.displayName cache entries and ensure new writes use the intended canonical key. | Current cache code persists only profile.displayName. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-004` | The changelog must name profile.name as the replacement and state when profile.displayName is removed, consistent with the selected rollout. | The configured deprecation duration is one release and the recorded field is profile.displayName. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| API profile field publication | api/profile.py:1 | verified |
| iOS profile decoding | ios/UserDTO.swift:1 | verified |
| Persisted profile cache key and migration behavior | cache/profile_cache.py:1 | verified |
| Deprecation release record | docs/changelog.py:1-2 | verified |
| Other external consumers and tests | No additional repository files or tests were found by the repository-wide search. | unknown outside this repository |
| Graph paths for IMP-001 | PATH-001: profile.displayName → profile.displayName | PATH-001: provider builtin; confidence lexical; location api/profile.py + ios/UserDTO.swift |
| Graph paths for IMP-002 | PATH-002: profile.displayName → profile.displayName | PATH-002: provider builtin; confidence lexical; location api/profile.py + cache/profile_cache.py |
| Graph paths for IMP-003 | PATH-003: profile.displayName → docs/changelog.py | PATH-003: provider builtin; confidence lexical; location api/profile.py + docs/changelog.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt 78519230511bdc822698b5d03f2c9154; sha256 4bac76d793cb77f426eed6847ce00d4092d768cc3e1a829db4f481eaa39fbcb2; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
