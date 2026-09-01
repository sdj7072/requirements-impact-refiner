# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | The profile API field changes from profile.displayName to profile.name. | The current iOS decoder may fail to populate the user's name. | iOS users and code consuming UserDTO. | An iOS build using the current decoder receives a response that contains only profile.name. | high | Either retain an old-key alias for the deprecation window or update the decoder in a coordinated release with an explicit compatibility fallback. | refining |
| `IMP-002` | The canonical cached profile field becomes profile.name. | Existing cached names may become unreadable or old and new entries may use divergent keys. | Users with profile data persisted before the rename and cache readers/writers. | Code reads a cache entry written under profile.displayName after switching to profile.name. | high | Define a one-time migration or dual-read strategy, and verify new writes use the selected canonical key. | refining |
| `IMP-003` | profile.displayName is deprecated in favor of profile.name. | Immediate removal can contradict the documented one-release deprecation policy and leave release notes inaccurate. | API consumers, release documentation, and maintainers enforcing compatibility policy. | profile.displayName is removed in the same release that introduces profile.name. | high | Keep the old field operational for one release and update changelog metadata, or explicitly approve and document a breaking hard cutover. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Rename profile.displayName to profile.name in api/profile.py. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Rename the published profile field from profile.displayName to profile.name, with the compatibility behavior across the API publisher, iOS decoder, persisted cache, and the documented one-release deprecation window explicitly selected before implementation. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The profile API currently publishes the field as profile.displayName. | verified | api/profile.py defines PROFILE_FIELD = "profile.displayName". |
| `INV-002` | The iOS client currently decodes the profile value from profile.displayName. | verified | ios/UserDTO.swift defines decodedField = "profile.displayName". |
| `INV-003` | Persisted profile cache entries currently use profile.displayName. | verified | cache/profile_cache.py defines CACHED_FIELD = "profile.displayName". |
| `INV-004` | Field deprecations are retained for one release. | verified | docs/changelog.py defines DEPRECATION_RELEASES = 1 and FIELD = "profile.displayName". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | api/profile.py defines PROFILE_FIELD = "profile.displayName". |
| `INV-002` | `REQ-001` | `IMP-001` | ios/UserDTO.swift defines decodedField = "profile.displayName". |
| `INV-003` | `REQ-001` | `IMP-002` | cache/profile_cache.py defines CACHED_FIELD = "profile.displayName". |
| `INV-004` | `REQ-001` | `IMP-003` | docs/changelog.py defines DEPRECATION_RELEASES = 1 and FIELD = "profile.displayName". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | interfaces | high | refining | unknown | The receipt finds only a lexical reference from api/profile.py to ios/UserDTO.swift; the exact runtime decoding behavior is not present in this minimal workspace. The matching field strings make client breakage plausible but not directly proven. | `INV-001`, `INV-002` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | data | high | refining | unknown | The receipt finds only a lexical reference from api/profile.py to cache/profile_cache.py; cache serialization and read behavior are absent. Existing and new cache entries plausibly require a migration policy, but runtime impact is not directly proven. | `INV-001`, `INV-003` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | compatibility | high | refining | unknown | The receipt finds only a lexical reference from api/profile.py to docs/changelog.py; release enforcement behavior is not present. The one-release constant and current field make an immediate-removal conflict plausible but not directly proven. | `INV-001`, `INV-004` | the pending decision | `AC-003` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| How should the rename handle the existing iOS decoder, persisted cache entries, and the one-release deprecation policy? | One-release compatibility migration | `IMP-001`, `IMP-002`, `IMP-003` | Publish profile.name as canonical while retaining profile.displayName for one release; update iOS to prefer name with an old-key fallback, migrate or dual-read cache data, and record the deprecation. This adds temporary compatibility code but minimizes breakage. |
| How should the rename handle the existing iOS decoder, persisted cache entries, and the one-release deprecation policy? | Coordinated hard cutover | `IMP-001`, `IMP-002`, `IMP-003` | Change API, iOS, cache, and changelog together and migrate existing cache data in the same release. This avoids a temporary alias but requires synchronized deployment and explicitly bypasses the normal deprecation window. |
| How should the rename handle the existing iOS decoder, persisted cache entries, and the one-release deprecation policy? | API-only hard rename | `IMP-001`, `IMP-002`, `IMP-003` | Edit only api/profile.py as literally requested. This is the smallest patch but knowingly risks the current iOS decoder, leaves cache keys stale, and conflicts with the stated deprecation policy. |

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
| `REQ-001` | Rename the published profile field from profile.displayName to profile.name, with the compatibility behavior across the API publisher, iOS decoder, persisted cache, and the documented one-release deprecation window explicitly selected before implementation. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | The selected rollout either keeps current iOS clients functional or explicitly coordinates their update before old-key removal. | Verify decoding behavior against payloads containing the new key and any supported old-key compatibility payload. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | Existing cached profile names remain readable, and new cache writes use the selected canonical representation. | Verify behavior for a pre-rename cache entry and a newly written post-rename entry. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-004` | The old field's removal timing and changelog metadata match the selected compatibility policy. | Verify DEPRECATION_RELEASES, FIELD, and the publisher behavior agree for the selected release strategy. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| API publisher | api/profile.py defines the current published field constant. | verified |
| iOS consumer | ios/UserDTO.swift decodes the current field constant. | verified |
| Persisted cache | cache/profile_cache.py stores the current field constant. | verified |
| Deprecation metadata | docs/changelog.py defines a one-release policy and the current field. | verified |
| Other consumers and tests | The mounted repository contains only the four supplied source files plus impact-refiner artifacts; no test suite or additional consumer code is present. | verified for this workspace, unknown for external consumers |
| Graph paths for IMP-001 | PATH-001: profile.displayName → profile.displayName | PATH-001: provider builtin; confidence lexical; location api/profile.py + ios/UserDTO.swift |
| Graph paths for IMP-002 | PATH-002: profile.displayName → profile.displayName | PATH-002: provider builtin; confidence lexical; location api/profile.py + cache/profile_cache.py |
| Graph paths for IMP-003 | PATH-003: profile.displayName → docs/changelog.py | PATH-003: provider builtin; confidence lexical; location api/profile.py + docs/changelog.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt 023627be9db16030df380f7c5ad07d3b; sha256 6f2cb656a58d6b26177725582f2a6436906a2b3fc6f04464f8cbc4af27942135; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Not ready |
