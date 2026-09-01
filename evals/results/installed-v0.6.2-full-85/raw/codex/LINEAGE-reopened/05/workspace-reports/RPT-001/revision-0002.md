# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 2 | 30bb24b8097c4832c5a9f01c8354d23f6541a788a3feb032d72b77a5effbb72a | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Remove profile.displayName across mobile and desktop clients. | The desktop cache may continue writing or expecting the field after the mobile decoder and server field are removed, invalidating the earlier compatibility treatment. | Desktop cache users and mixed-version mobile/desktop deployments. | The field is removed while a released desktop client still serializes profile.displayName. | high | Select and verify a desktop migration and rollout strategy before treating the one-release preservation window as sufficient. | refining |
| `IMP-002` | Stop exposing profile.displayName through the mobile decoder. | Removing only the mobile decode path leaves the field active in another client and does not complete the field removal. | Mobile profile behavior and cross-client consistency. | decodeDisplayName is removed without addressing the desktop serializer. | medium | Keep the mobile removal criterion, but plan it as part of an all-client field-removal boundary. | refining |
| `IMP-003` | Remove the profile.displayName field from repository clients. | Desktop cache serialization can preserve stale data, fail after schema removal, or reintroduce the removed field. | Desktop cache reads and writes and any synchronization using cached profiles. | The migration expires or the server field disappears while desktop serialization remains. | high | Reopen regression analysis, address every client reference, and test cache migration plus mixed-version operation. | refining |
| `IMP-004` | Stop serializing profile.displayName in the desktop profile cache. | Existing cached records may retain the field or become incompatible with readers after serialization changes. | Persisted desktop profile-cache entries and desktop cache consumers. | Desktop serialization changes or the migration preservation window ends without a cache migration policy. | high | Choose whether to remove, transform, or temporarily retain desktop cache data and verify existing-cache upgrade behavior. | refining |
| `IMP-005` | Continue RPT-001 without substituting chat-response bytes for persisted canonical Markdown. | Using first.final.txt or normalized conversation text as predecessor content would create a false report lineage and incorrect previous hash. | RPT-001 revision identity and auditability. | A continuation reconstructs predecessor Markdown from first.final.txt instead of the file selected by current.json. | high | Use revision-0001.md exactly as selected by current.json and verify its SHA-256 before publishing revision 2. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Record an impact report for removing a profile field beginning in mobile/ProfileDecoder.swift at decodeDisplayName. The supplied migration evidence supports resolving the client compatibility impact. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Remove profile.displayName from all in-repository client behavior, beginning with mobile/ProfileDecoder.swift at decodeDisplayName and now including direct serialization in desktop/ProfileCache.swift; do not treat the existing one-release preservation setting as sufficient compatibility resolution until a desktop cache migration and rollout strategy is selected. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-002` | The mobile profile decoder currently reads the displayName payload key for profile.displayName. | verified | mobile/ProfileDecoder.swift declares decodedField = "profile.displayName" and decodeDisplayName returns payload["displayName"]. |
| `INV-001` | The migration currently preserves profile.displayName for one release. | verified | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |
| `INV-003` | The desktop profile cache currently serializes profile.displayName directly. | verified | desktop/ProfileCache.swift declares serializedField = "profile.displayName". |
| `INV-004` | profile.displayName currently has at least two in-repository client behaviors: mobile decoding and desktop cache serialization. | verified | Direct source inspection finds the field in mobile/ProfileDecoder.swift and desktop/ProfileCache.swift, in addition to migration metadata. |
| `INV-005` | Persisted impact-report lineage is selected by RPT-001/current.json and uses the exact bytes of its canonical Markdown target, not chat-response text. | verified | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 30bb24b8097c4832c5a9f01c8354d23f6541a788a3feb032d72b77a5effbb72a, which matches the independently computed hash of that exact file. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-002` | `REQ-001` | `IMP-002` | mobile/ProfileDecoder.swift declares decodedField = "profile.displayName" and decodeDisplayName returns payload["displayName"]. |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-004` | migrations/profile_field.py sets PRESERVE_RELEASES = 1 and FIELD = "profile.displayName". |
| `INV-003` | `REQ-001` | `IMP-001`, `IMP-003`, `IMP-004` | desktop/ProfileCache.swift declares serializedField = "profile.displayName". |
| `INV-004` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | Direct source inspection finds the field in mobile/ProfileDecoder.swift and desktop/ProfileCache.swift, in addition to migration metadata. |
| `INV-005` | `REQ-001` | `IMP-005` | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md with SHA-256 30bb24b8097c4832c5a9f01c8354d23f6541a788a3feb032d72b77a5effbb72a, which matches the independently computed hash of that exact file. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | compatibility | high | refining | unknown | New source evidence shows desktop/ProfileCache.swift serializes profile.displayName directly, so the prior one-release compatibility mitigation does not by itself establish safe removal for every client. Receipt coverage remains provider-limited. | `INV-001`, `INV-003`, `INV-004` | the pending decision | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | functionality | medium | refining | unknown | The intended mobile decoder removal remains in scope, but the newly discovered desktop behavior expands the field-removal boundary beyond mobile/ProfileDecoder.swift. | `INV-002`, `INV-004` | the pending decision | `AC-003` |
| `IMP-003` | `REQ-001` | regression | high | refining | unknown | The earlier bounded client scope is contradicted by desktop/ProfileCache.swift, which directly serializes profile.displayName. Graph providers remain unavailable. | `INV-003`, `INV-004` | the pending decision | `AC-004` |
| `IMP-004` | `REQ-001` | data | high | refining | unknown | desktop/ProfileCache.swift directly names profile.displayName as serializedField, establishing a distinct persisted-cache data impact. Receipt coverage is lexical and provider-limited. | `INV-003`, `INV-001` | the pending decision | `AC-005` |
| `IMP-005` | `REQ-001` | operations | high | mitigated | unknown | The receipt lexically links desktop/ProfileCache.swift to first.final.txt, but first.final.txt is a chat-response artifact and not canonical report lineage. Exact current.json selection and SHA-256 verification mitigate predecessor reconstruction. | `INV-005` | the pending decision | `AC-006` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| How should desktop/ProfileCache.swift and existing cached profile.displayName data be handled before the field is removed? | Migrate desktop in the same change | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Removes mobile decoding and desktop serialization together and validates existing-cache upgrades; largest immediate change, but gives the clearest compatibility boundary. |
| How should desktop/ProfileCache.swift and existing cached profile.displayName data be handled before the field is removed? | Stage desktop migration and extend preservation | `IMP-001`, `IMP-003`, `IMP-004` | Ships a desktop cache migration first and retains profile.displayName beyond the current one-release window; safer for released clients but delays final removal. |
| How should desktop/ProfileCache.swift and existing cached profile.displayName data be handled before the field is removed? | Defer field removal | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Keeps current behavior until desktop cache lifecycle evidence is available; lowest immediate compatibility risk but postpones the requested cleanup. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | `IMP-001` |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Remove mobile decoding support for profile.displayName, beginning at decodeDisplayName in mobile/ProfileDecoder.swift, while preserving the field for one migration release so already-released clients remain compatible during the transition. | the pending decision | none | Controller-created refinement revision. The historical decision remains authoritative in the prior immutable revision. |
| `REQ-001` | Remove profile.displayName from all in-repository client behavior, beginning with mobile/ProfileDecoder.swift at decodeDisplayName and now including direct serialization in desktop/ProfileCache.swift; do not treat the existing one-release preservation setting as sufficient compatibility resolution until a desktop cache migration and rollout strategy is selected. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Before the configured profile.displayName preservation window expires, both the mobile decoder and desktop serializer are verified compatible with removal or retired, and no supported client still requires the field. | PRESERVE_RELEASES is currently 1, but the newly identified desktop dependency means that duration alone does not establish mixed-client safety. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-003` | A selected rollout strategy explicitly covers released desktop clients that serialize profile.displayName and states when field removal becomes safe. | desktop/ProfileCache.swift proves the compatibility scope includes a second client. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-002` | mobile/ProfileDecoder.swift no longer declares decodedField for profile.displayName or decodeDisplayName. | The mobile declarations remain the original bounded removal point. |
| `AC-004` | `REQ-001` | `IMP-003` | `INV-004` | After the chosen migration step, repository searches and builds show no unintended profile.displayName dependency in mobile or desktop code; only deliberate transitional migration metadata may remain. | Current inspection finds active client references in both mobile/ProfileDecoder.swift and desktop/ProfileCache.swift. |
| `AC-005` | `REQ-001` | `IMP-004` | `INV-003` | Existing desktop cache entries upgrade safely, and new desktop cache writes no longer serialize profile.displayName once the selected transition point is reached. | desktop/ProfileCache.swift currently serializes the field directly, so both existing and new cache data require an explicit outcome. |
| `AC-006` | `REQ-001` | `IMP-005` | `INV-005` | Revision 2 records previous SHA-256 30bb24b8097c4832c5a9f01c8354d23f6541a788a3feb032d72b77a5effbb72a from the exact revision-0001.md selected by current.json. | The independently computed SHA-256 matches the digest stored in current.json. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Canonical predecessor lineage | .requirements-impact-refiner/reports/RPT-001/current.json selects revision-0001.md; its exact SHA-256 is 30bb24b8097c4832c5a9f01c8354d23f6541a788a3feb032d72b77a5effbb72a. | Verified from persisted canonical bytes; conversation text and first.final.txt were not used as predecessor content. |
| Mobile profile decoding | mobile/ProfileDecoder.swift declares profile.displayName and decodeDisplayName. | High for direct source inspection. |
| Desktop cache serialization | desktop/ProfileCache.swift declares serializedField = "profile.displayName". | High for direct source inspection; the full cache lifecycle is not visible in the one-line file. |
| Migration preservation | migrations/profile_field.py sets PRESERVE_RELEASES = 1 for profile.displayName. | High for the configuration value; insufficient by itself to establish safety across the newly identified desktop client. |
| Graph evidence selection | PATH-001 covers desktop/ProfileCache.swift to migrations/profile_field.py, PATH-002 covers desktop/ProfileCache.swift to mobile/ProfileDecoder.swift, and PATH-003 exposes first.final.txt as a noncanonical artifact path. | Provider-limited and lexical; one unknown frontier remains because ast-grep, codegraph, and scip are unavailable. |
| Graph paths for IMP-001 | PATH-001: serializedField → profile.displayName &#124;&#124; PATH-002: serializedField → decodeDisplayName | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Graph paths for IMP-002 | PATH-002: serializedField → decodeDisplayName | PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Graph paths for IMP-003 | PATH-001: serializedField → profile.displayName &#124;&#124; PATH-002: serializedField → decodeDisplayName | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location desktop/ProfileCache.swift + mobile/ProfileDecoder.swift |
| Graph paths for IMP-004 | PATH-001: serializedField → profile.displayName | PATH-001: provider builtin; confidence lexical; location desktop/ProfileCache.swift + migrations/profile_field.py |
| Graph paths for IMP-005 | PATH-003: serializedField → first.final.txt | PATH-003: provider builtin; confidence lexical; location desktop/ProfileCache.swift + first.final.txt |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 4 nodes / 12 edges · 1 unknown frontiers | provider_limited; receipt 1b4458f5242d69e5fa8cdb9d56b11de8; sha256 dc200e5b2f45c118796bea0aaa8aeb14b184db7614139b24046d3ba751a6c7d8; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-002`, `INV-001`, `INV-003`, `INV-004`, `INV-005`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006` | Not ready |
