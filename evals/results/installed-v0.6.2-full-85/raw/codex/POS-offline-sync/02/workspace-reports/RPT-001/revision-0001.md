# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Reconnect synchronization of offline.edits | Queued edits could bypass model normalization and timestamp stamping. | Offline-created records and edits replayed after reconnect. | The app reconnects with one or more pending queue items. | high | Drain the queue only through models/record.py and verify every replayed mutation uses that path. | mitigated |
| `IMP-002` | Ordered reconnect replay | Continuing after a failed edit or acknowledging too early can reorder dependent edits or lose local changes. | The failed queue item and all later locally created edits. | A record mutation fails partway through reconnect synchronization. | high | Process sequentially, acknowledge after success, and stop while retaining the failed suffix. | detected |
| `IMP-003` | Reconnect reconciliation against server deletions | An offline edit can resurrect a server-deleted record, especially after its tombstone expires. | Records deleted while a client remains offline. | A queued edit targets a record with a live or already-expired deletion tombstone. | high | Reject live-tombstone conflicts and surface expired-window conflicts instead of silently recreating records. | detected |
| `IMP-004` | Timestamping of replayed offline edits | Using a client-supplied or queue-time timestamp can violate model ownership and alter conflict resolution. | Consumers that compare updated_at values. | A queued edit is replayed after reconnect. | medium | Have models/record.py stamp updated_at when the replay mutation is applied and test that client timestamps do not override it. | detected |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Sync offline.edits through models/record.py when the app reconnects. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | When the app reconnects, synchronize the offline.edits queue by replaying each pending edit through the canonical models/record.py mutation path, in the queue's preserved local creation order. models/record.py remains the owner of updated_at stamping. A queue item is removed only after its record mutation succeeds; on failure, retain that item and all later items for retry. Reconnect reconciliation must honor any still-live server tombstone and must not silently recreate a record merely because its 24-hour tombstone has expired. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Mutations of offline.edits that pass through models/record.py receive updated_at from that model path. | verified | Direct inspection: models/record.py defines STREAM = "offline.edits" and STAMPED = "updated_at". |
| `INV-002` | The client queue preserves local edit creation order and provides no stronger conflict ordering guarantee. | verified | Direct inspection: client/queue.py defines PRESERVES = "local creation order only" for offline.edits. |
| `INV-003` | Server deletion tombstones for offline.edits are retained for 24 hours. | verified | Direct inspection: server/tombstones.py defines TOMBSTONE_HOURS = 24 and references offline.edits. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-004` | Direct inspection: models/record.py defines STREAM = "offline.edits" and STAMPED = "updated_at". |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | Direct inspection: client/queue.py defines PRESERVES = "local creation order only" for offline.edits. |
| `INV-003` | `REQ-001` | `IMP-003` | Direct inspection: server/tombstones.py defines TOMBSTONE_HOURS = 24 and references offline.edits. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | high | mitigated | unknown | The requested mechanics select models/record.py as the reconnect replay path; PATH-001 is only a lexical offline.edits link and cannot prove a callable integration. | `INV-001`, `INV-002` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | state/concurrency | high | detected | unknown | client/queue.py guarantees creation order only; no source defines acknowledgement or partial-failure behavior. PATH-001 is lexical and provider coverage is limited. | `INV-002` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | data | high | detected | unknown | server/tombstones.py retains tombstones for 24 hours; PATH-002 is only a lexical offline.edits link. Behavior after expiry and the tombstone lookup API are absent. | `INV-003`, `INV-002` | `DEC-001` | `AC-003` |
| `IMP-004` | `REQ-001` | compatibility | medium | detected | unknown | models/record.py names updated_at and client/queue.py names ordering, but PATH-001 is lexical and no executable stamping behavior exists in the supplied source. | `INV-001`, `INV-002` | `DEC-001` | `AC-004` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Replay offline.edits sequentially through models/record.py on reconnect. | `REQ-001` | none | The user explicitly selected the canonical model path; the remaining ordering, retry, tombstone, and timestamp risks are implementation constraints rather than alternate mechanics. |

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
| new | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | When the app reconnects, synchronize the offline.edits queue by replaying each pending edit through the canonical models/record.py mutation path, in the queue's preserved local creation order. models/record.py remains the owner of updated_at stamping. A queue item is removed only after its record mutation succeeds; on failure, retain that item and all later items for retry. Reconnect reconciliation must honor any still-live server tombstone and must not silently recreate a record merely because its 24-hour tombstone has expired. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Given pending offline.edits at reconnect, every applied edit invokes the models/record.py mutation path and no queue item is applied directly. | Required verification: an integration test observes the record mutation boundary. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | Queued edits are attempted in local creation order; each successful item is removed once, and the first failure leaves that item plus every later item queued in the same order. | Required verification: success, middle-failure, and retry cases use deterministic queue fixtures. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | A queued edit targeting a live tombstone is not applied; a target whose tombstone can no longer be proven within the 24-hour window is surfaced as a conflict and is not silently recreated. | Required verification: boundary cases immediately before, at, and after 24 hours. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-001` | A successfully replayed edit receives updated_at from models/record.py at apply time, and any client-provided updated_at cannot override it. | Required verification: a fixed model clock and a conflicting client timestamp. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Reconnect draining of the client offline.edits queue | client/queue.py names offline.edits and guarantees local creation order only. | high for the constant; unknown for executable behavior |
| Canonical record mutation and updated_at stamping | models/record.py names offline.edits and updated_at. | high for the constants; unknown for executable behavior |
| Server tombstone reconciliation during replay | server/tombstones.py defines a 24-hour retention window; the exact lookup API is absent. | medium for retention; unknown for reconciliation |
| Graph paths for IMP-001 | PATH-001: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py |
| Graph paths for IMP-002 | PATH-001: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py |
| Graph paths for IMP-003 | PATH-002: client/queue.py → offline.edits | PATH-002: provider builtin; confidence lexical; location client/queue.py + server/tombstones.py |
| Graph paths for IMP-004 | PATH-001: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt fca317dc71f08e9f89d0d894fe8772a7; sha256 54ee7d96f09c74a1298347bbe5534576ade5516f19fa69fbf17ea9c6bbe974ba; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Ready for implementation planning; preserve the explicit replay mechanic and satisfy the ordering, retry, tombstone, and timestamp criteria. |
