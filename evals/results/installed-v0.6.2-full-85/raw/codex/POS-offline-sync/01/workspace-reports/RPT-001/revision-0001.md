# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Reconnect now drains offline.edits through the record mutation path. | A partial failure or retry could duplicate, skip, or reorder edits, and replay-time updated_at values could become the accidental ordering key. | Queued record mutations and conflict resolution after reconnect. | Connectivity returns while one or more local edits are pending, especially if replay is interrupted. | high | Replay sequentially by durable queue identity/local creation order, acknowledge only successful applications, and make repeated application idempotent without using freshly stamped updated_at to reorder the batch. | refining |
| `IMP-002` | Offline edits may arrive after a disconnect of arbitrary duration. | An edit replayed after its record's 24-hour tombstone expires can recreate a server-deleted record. | Records deleted while another client remains offline. | Reconnect and replay occur more than 24 hours after the server-side deletion. | high | Carry stable record identity/delete knowledge through replay and reject or explicitly conflict stale edits so tombstone expiry cannot turn an update into creation. | refining |
| `IMP-003` | Reconnect replay uses the same record path as other offline.edits. | If the queue or reconnect layer also stamps timestamps, clients may observe inconsistent last-write ordering. | Consumers that compare or display updated_at. | An offline edit is synchronized after reconnect. | medium | Keep updated_at assignment exclusively in models/record.py and test that replay does not preserve or create a competing client timestamp. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Sync offline.edits through models/record.py when the app reconnects. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | When connectivity is restored, replay queued offline.edits through the models/record.py record mutation path in the queue's existing local creation order. The record path remains responsible for stamping updated_at. Reconnect replay must be safe across retries/partial failures and must not recreate a record deleted under the server's 24-hour tombstone policy. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | client/queue.py preserves queued offline edits in local creation order. | verified | Repository evidence and current client/queue.py both state PRESERVES = "local creation order only". |
| `INV-002` | models/record.py is the authority that stamps updated_at for offline.edits. | verified | Repository evidence and current models/record.py identify offline.edits and STAMPED = "updated_at". |
| `INV-003` | Server deletion tombstones are retained for 24 hours. | verified | Repository evidence and current server/tombstones.py set TOMBSTONE_HOURS = 24. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | Repository evidence and current client/queue.py both state PRESERVES = "local creation order only". |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-003` | Repository evidence and current models/record.py identify offline.edits and STAMPED = "updated_at". |
| `INV-003` | `REQ-001` | `IMP-002` | Repository evidence and current server/tombstones.py set TOMBSTONE_HOURS = 24. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | state/concurrency | high | refining | unknown | PATH-001 is only a lexical offline.edits link from client/queue.py to models/record.py; supplied evidence confirms ordering and timestamp ownership but retry and acknowledgement behavior are absent. | `INV-001`, `INV-002` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | data | high | refining | unknown | PATH-002 is only a lexical offline.edits link from client/queue.py to server/tombstones.py; retention is verified as 24 hours, but stale-edit rejection/delete-version behavior is not evidenced. | `INV-001`, `INV-003` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | compatibility | medium | refining | unknown | PATH-001 is a lexical queue-to-record link; models/record.py timestamp ownership is verified, but actual reconnect behavior is not present. | `INV-002`, `INV-001` | `DEC-001` | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Replay offline.edits through models/record.py in existing local creation order on reconnect. | `REQ-001` | none | The request specifies these mechanics explicitly. Record-path timestamp ownership is preserved, while retry safety and tombstone-aware rejection are required constraints rather than alternative product choices. |

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
| `REQ-001` | When connectivity is restored, replay queued offline.edits through the models/record.py record mutation path in the queue's existing local creation order. The record path remains responsible for stamping updated_at. Reconnect replay must be safe across retries/partial failures and must not recreate a record deleted under the server's 24-hour tombstone policy. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | On reconnect, pending offline.edits are offered to models/record.py one at a time in durable local creation order; successful edits are removed, a failed edit and later edits remain queued, and retrying cannot apply an already acknowledged edit twice. | Required verification: tests covering multiple edits, an interrupted drain, and a second reconnect. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | Replaying an offline update for a server-deleted record does not create that record, including when reconnect happens after the 24-hour tombstone retention window; the edit remains rejected or surfaced as a conflict. | Required verification: tests at less than, exactly at, and greater than 24 hours after deletion. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-002` | Every replayed offline edit receives updated_at from models/record.py, and the reconnect/queue layer neither stamps nor uses that replay-time value to change queue order. | Required verification: assert record-path stamping and unchanged local replay order under equal or non-monotonic client timestamps. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| client/queue.py reconnect detection, ordered drain, acknowledgement, and retry behavior. | Current file only declares local creation order and offline.edits linkage. | High that this is the reconnect entry point; implementation surface is otherwise unspecified. |
| models/record.py application of offline edits and updated_at authority. | Current file declares offline.edits and updated_at stamping. | High based on supplied evidence; graph linkage is only lexical. |
| server/tombstones.py stale-delete protection for replayed edits. | Current file declares 24-hour retention and offline.edits linkage. | High based on supplied evidence; graph linkage is only lexical. |
| Automated tests for ordered replay, retries, timestamp authority, and expired tombstones. | No test files or framework are present in the repository. | High that tests are required; framework choice is not evidenced. |
| Graph paths for IMP-001 | PATH-001: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py |
| Graph paths for IMP-002 | PATH-002: client/queue.py → offline.edits | PATH-002: provider builtin; confidence lexical; location client/queue.py + server/tombstones.py |
| Graph paths for IMP-003 | PATH-001: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt cf0ea2865b5d2890f4e02739e638add7; sha256 cf6556f21948a92fbd6524a4669c70c29a1790c17c51d3f4fa324795bbf69ca4; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003` | `AC-001`, `AC-002`, `AC-003` | Ready for planning |
