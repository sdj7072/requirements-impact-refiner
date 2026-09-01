# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Reconnect replay for offline.edits | Edits could bypass canonical updated_at stamping or receive stamps in an order that changes the user's final value. | Offline users reconnecting with more than one queued edit | The client drains its offline queue after connectivity returns. | high | Replay serially in local creation order and invoke the record model boundary for every item. | mitigated |
| `IMP-002` | Applying queued edits to records that may have been deleted while the client was offline | A late reconnect edit could recreate a deleted record or overwrite deletion state. | Records edited offline and deleted elsewhere before reconnect | Replay targets a record with a retained tombstone or crosses the 24-hour retention edge. | high | Check deletion authority before the model write and reject or acknowledge-without-write rather than resurrecting the record. | mitigated |
| `IMP-003` | Queue acknowledgement during reconnect | Removing work before acceptance can lose edits; retrying an accepted prefix can duplicate effects. | Clients whose reconnect replay fails or disconnects partway through | An exception or connectivity loss occurs after some edits have been sent. | high | Acknowledge and remove one accepted edit at a time, retain the failed suffix, and deduplicate retries by edit identity. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Sync offline.edits through models/record.py when the app reconnects. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | When the application reconnects, replay queued offline.edits in their preserved local creation order. Every replayed edit must enter through the models/record.py record-application boundary so updated_at is assigned by the canonical record path. Replay must consult server tombstones before applying a write and must not recreate a record whose deletion is still authoritative, including at the 24-hour retention boundary. Remove a queued edit only after that edit is accepted; on failure, retain the failed edit and every later edit for retry, and make retry behavior idempotent. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Queued offline.edits retain local creation order during reconnect replay. | verified | client/queue.py declares PRESERVES = "local creation order only" and STREAM_LINK = "offline.edits". |
| `INV-002` | The record model is the canonical boundary that stamps updated_at for offline.edits. | verified | models/record.py declares STREAM = "offline.edits" and STAMPED = "updated_at". |
| `INV-003` | Deletion tombstones are retained for 24 hours. | verified | server/tombstones.py declares TOMBSTONE_HOURS = 24 and STREAM_REF = "offline.edits". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | client/queue.py declares PRESERVES = "local creation order only" and STREAM_LINK = "offline.edits". |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-003` | models/record.py declares STREAM = "offline.edits" and STAMPED = "updated_at". |
| `INV-003` | `REQ-001` | `IMP-002` | server/tombstones.py declares TOMBSTONE_HOURS = 24 and STREAM_REF = "offline.edits". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | high | mitigated | unknown | PATH-001 connects client/queue.py to models/record.py only through the scan's built-in fallback; the user explicitly selected replay through models/record.py. | `INV-001`, `INV-002` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | data | high | mitigated | unknown | PATH-002 connects client/queue.py to server/tombstones.py only through the scan's built-in fallback; server/tombstones.py fixes retention at 24 hours. | `INV-001`, `INV-003` | none | `AC-002` |
| `IMP-003` | `REQ-001` | state/concurrency | high | mitigated | unknown | The queue preserves order, but the supplied implementation contains no acknowledgement or retry contract; PATH-001 is based only on the scan's built-in fallback. | `INV-001`, `INV-002` | none | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Route every reconnect replay item through models/record.py. | `REQ-001` | `IMP-001` | This is the exact mechanic requested by the user and preserves the existing updated_at ownership boundary. |

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
| `REQ-001` | When the application reconnects, replay queued offline.edits in their preserved local creation order. Every replayed edit must enter through the models/record.py record-application boundary so updated_at is assigned by the canonical record path. Replay must consult server tombstones before applying a write and must not recreate a record whose deletion is still authoritative, including at the 24-hour retention boundary. Remove a queued edit only after that edit is accepted; on failure, retain the failed edit and every later edit for retry, and make retry behavior idempotent. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | Given multiple queued offline.edits, reconnect invokes the record application boundary once per edit in local creation order, and each accepted edit receives its updated_at from that boundary. | Verify with a deterministic clock and a spy/fake record applier. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | A queued edit targeting a tombstoned record does not recreate or update the record at, before, or after the 24-hour retention boundary; the outcome is explicit and test-covered. | Verify tombstone ages just below, exactly at, and just above 24 hours. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-001` | If replay fails on item N, accepted items before N are not reapplied, while item N and all later items remain queued in their original order; retrying an accepted edit identity has no duplicate effect. | Verify with an injected failure in the middle of a three-edit queue and a subsequent retry. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| client/queue.py reconnect drain and acknowledgement semantics | The file currently declares only offline.edits linkage and local creation-order preservation. | high |
| models/record.py canonical offline edit application and updated_at stamping | The file explicitly associates offline.edits with updated_at. | high |
| server/tombstones.py deletion-authority check at the 24-hour boundary | The file explicitly associates offline.edits with a 24-hour tombstone constant. | high |
| Graph paths for IMP-001 | PATH-001: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py |
| Graph paths for IMP-002 | PATH-002: client/queue.py → offline.edits | PATH-002: provider builtin; confidence lexical; location client/queue.py + server/tombstones.py |
| Graph paths for IMP-003 | PATH-001: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt d32a276a23984341174ed8887e5d4b67; sha256 1ac1b3533608f0ff539e30c59bc4ecde9ee4f0d02fd9eee7751a2bcd487b5f8b; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Ready for planning and implementation; validate ordering, timestamp ownership, tombstone boundaries, partial failure, and retry idempotency. |
