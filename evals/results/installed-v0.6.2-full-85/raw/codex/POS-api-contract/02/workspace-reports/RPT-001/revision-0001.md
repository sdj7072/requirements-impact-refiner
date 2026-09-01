# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | API profile field rename to profile.name | Existing iOS clients may decode no display name. | ios/UserDTO.swift and released clients using profile.displayName | The API stops publishing profile.displayName before consumers migrate. | high | Choose either a one-release dual-publish period or an explicitly coordinated breaking release. | refining |
| `IMP-002` | Profile cache field migration | Previously cached names can become unreadable or coexist under two keys. | cache/profile_cache.py and existing persisted cache entries | Writers/readers switch keys without fallback or migration. | high | Define read-old/write-new behavior or invalidate/migrate existing cache data. | refining |
| `IMP-003` | Removal timing for profile.displayName | The release violates the repository's one-release deprecation policy. | API consumers and release documentation | profile.displayName is removed in the same release that profile.name is introduced. | high | Retain the deprecated alias for one release and document its later removal, or explicitly approve a policy exception. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Rename profile.displayName to profile.name in api/profile.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Rename the API profile field from profile.displayName to profile.name while explicitly choosing how the existing iOS decoder and persisted cache key transition during the repository's one-release deprecation window. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The API currently publishes the profile value under profile.displayName. | verified | api/profile.py:1 sets PROFILE_FIELD = "profile.displayName". |
| `INV-002` | The iOS DTO currently decodes the profile value from profile.displayName. | verified | ios/UserDTO.swift:1 sets decodedField = "profile.displayName". |
| `INV-003` | The profile cache currently persists the value under profile.displayName. | verified | cache/profile_cache.py:1 sets CACHED_FIELD = "profile.displayName". |
| `INV-004` | Deprecated profile fields remain compatible for one release. | verified | docs/changelog.py:1 sets DEPRECATION_RELEASES = 1; line 2 identifies profile.displayName as the field. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | api/profile.py:1 sets PROFILE_FIELD = "profile.displayName". |
| `INV-002` | `REQ-001` | `IMP-001` | ios/UserDTO.swift:1 sets decodedField = "profile.displayName". |
| `INV-003` | `REQ-001` | `IMP-002` | cache/profile_cache.py:1 sets CACHED_FIELD = "profile.displayName". |
| `INV-004` | `REQ-001` | `IMP-003` | docs/changelog.py:1 sets DEPRECATION_RELEASES = 1; line 2 identifies profile.displayName as the field. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | interfaces | high | refining | unknown | The supplied files show that api/profile.py publishes profile.displayName and ios/UserDTO.swift decodes that exact field; the graph provider relationship is a built-in fallback and needs behavioral verification. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | data | high | refining | unknown | The supplied files show cache/profile_cache.py persists profile.displayName while the requested API contract would publish profile.name; the graph provider relationship is a built-in fallback and needs behavioral verification. | `INV-001`, `INV-003` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | compatibility | high | refining | unknown | The supplied files show docs/changelog.py sets DEPRECATION_RELEASES = 1 and identifies profile.displayName; the graph provider relationship is a built-in fallback and needs policy verification. | `INV-001`, `INV-004` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| How should the rename handle the existing consumers and the one-release deprecation policy? | Stage the rename for one release | `IMP-001`, `IMP-002`, `IMP-003` | Publish profile.name while retaining profile.displayName for one release; update consumers and cache compatibility now, then remove the old field later. |
| How should the rename handle the existing consumers and the one-release deprecation policy? | Coordinate an immediate breaking rename | `IMP-001`, `IMP-002`, `IMP-003` | Update the API, iOS decoder, and cache key together now, but make this a breaking release and explicitly waive the one-release policy. |
| How should the rename handle the existing consumers and the one-release deprecation policy? | Change only api/profile.py | `IMP-001`, `IMP-002`, `IMP-003` | Matches the narrow file request, but knowingly breaks the current decoder/cache contract and violates the declared deprecation window. |

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
| `REQ-001` | Rename the API profile field from profile.displayName to profile.name while explicitly choosing how the existing iOS decoder and persisted cache key transition during the repository's one-release deprecation window. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | During the chosen transition, supported iOS clients decode the same profile name value the API publishes. | Verify the publisher and Swift decoder against fixtures covering the selected old/new field behavior. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | Existing cached profile names remain readable or are deliberately migrated/invalidated, and new writes use the selected canonical key. | Verify cache reads and writes with entries stored under profile.displayName and profile.name. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-004` | The implementation either preserves profile.displayName for one release or records an explicit breaking-change policy exception. | Verify API output and changelog/deprecation metadata for the selected release behavior. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| API publisher | api/profile.py defines PROFILE_FIELD. | verified |
| iOS consumer | ios/UserDTO.swift decodes the old field. | verified |
| Persisted cache format | cache/profile_cache.py uses the old field as CACHED_FIELD. | verified |
| Release compatibility policy | docs/changelog.py declares one deprecation release for the old field. | verified |
| Graph paths for IMP-001 | PATH-001: profile.displayName → profile.displayName | PATH-001: provider builtin; confidence lexical; location api/profile.py + ios/UserDTO.swift |
| Graph paths for IMP-002 | PATH-002: profile.displayName → profile.displayName | PATH-002: provider builtin; confidence lexical; location api/profile.py + cache/profile_cache.py |
| Graph paths for IMP-003 | PATH-003: profile.displayName → docs/changelog.py | PATH-003: provider builtin; confidence lexical; location api/profile.py + docs/changelog.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt 1cf22c6a7834b33439abb7dd2a7a7316; sha256 597542ec2b6e55b4268fa540094309cc0d66fb5576508c86bbea0017bfbb3918; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
