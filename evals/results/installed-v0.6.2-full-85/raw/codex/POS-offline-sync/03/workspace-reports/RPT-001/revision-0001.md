# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Reconnect replay of offline.edits | An edit replayed after its target's tombstone has expired can recreate data that the server previously deleted. | Users and server records involved in delete-versus-offline-edit conflicts. | A client remains offline longer than 24 hours and later replays an edit for a deleted record. | critical | Choose and enforce an explicit late-edit policy, with a test covering replay just inside and just outside the retention window. | blocked |
| `IMP-002` | Routing queued edits through models/record.py | Replay-time updated_at values can replace the edits' original chronology and alter last-write-wins outcomes. | Records with concurrent server changes or multiple offline edits. | Queued edits are stamped when replayed after reconnect. | high | Keep queue order as the replay sequence, distinguish local creation metadata from server updated_at, and test concurrent-update ordering. | detected |
| `IMP-003` | Automatic reconnect synchronization | A disconnect during replay can apply an edit twice or drop remaining edits if acknowledgement and dequeue timing are not atomic. | Clients reconnecting over unstable networks and records receiving replayed edits. | Connectivity fails after a server write but before the client records acknowledgement. | high | Give queued edits stable identities, acknowledge each successful application, dequeue only acknowledged edits, and verify retry idempotency. | detected |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Sync offline.edits through models/record.py when the app reconnects. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | When connectivity is restored, replay queued offline.edits in their preserved local creation order through the models/record.py record-write path so normal updated_at stamping is applied, while defining safe behavior for retries and edits that arrive after the server's 24-hour tombstone retention window. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The client queue preserves offline edits in local creation order. | verified | client/queue.py declares PRESERVES = "local creation order only" and STREAM_LINK = "offline.edits". |
| `INV-002` | Writes to the offline.edits record path use updated_at as the record stamp. | verified | models/record.py declares STREAM = "offline.edits" and STAMPED = "updated_at". |
| `INV-003` | Server tombstones for offline.edits are retained for 24 hours. | verified | server/tombstones.py declares TOMBSTONE_HOURS = 24 and STREAM_REF = "offline.edits". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | client/queue.py declares PRESERVES = "local creation order only" and STREAM_LINK = "offline.edits". |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-003` | models/record.py declares STREAM = "offline.edits" and STAMPED = "updated_at". |
| `INV-003` | `REQ-001` | `IMP-001` | server/tombstones.py declares TOMBSTONE_HOURS = 24 and STREAM_REF = "offline.edits". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | data | critical | blocked | unknown | The supplied files declare a 24-hour tombstone window and offline replay ordering, but the graph provider was unavailable, so the transitive runtime behavior is unverified. | `INV-001`, `INV-003` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | state/concurrency | high | detected | unknown | The supplied files declare updated_at stamping and local creation order, but the graph provider was unavailable and no executable write path exists. | `INV-001`, `INV-002` | the pending decision | `AC-002`, `AC-003` |
| `IMP-003` | `REQ-001` | operations | high | detected | unknown | The repository contains no reconnect acknowledgement, retry, cursor, or idempotency implementation; only stream and ordering constants are present. | `INV-001`, `INV-002` | the pending decision | `AC-004` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What should happen when an offline edit is replayed after the target record's 24-hour tombstone has expired? | Reject and surface a conflict | `IMP-001` | Prevents silent resurrection but requires a client-visible conflict/recovery path. |
| What should happen when an offline edit is replayed after the target record's 24-hour tombstone has expired? | Extend tombstone retention | `IMP-001` | Allows more offline clients to sync safely but increases server storage and still needs a finite cutoff policy. |
| What should happen when an offline edit is replayed after the target record's 24-hour tombstone has expired? | Allow recreation | `IMP-001` | Keeps replay simple but can silently undo a server-side deletion. |

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
| `REQ-001` | When connectivity is restored, replay queued offline.edits in their preserved local creation order through the models/record.py record-write path so normal updated_at stamping is applied, while defining safe behavior for retries and edits that arrive after the server's 24-hour tombstone retention window. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-003` | Reconnect replay enforces the selected policy for edits targeting deleted records both before and after the 24-hour tombstone expiry. | Required to close the delete-versus-late-edit ambiguity created by finite tombstone retention. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | Every successfully replayed offline.edit is applied through models/record.py and receives the normal updated_at stamp exactly once per logical edit. | Directly expresses the requested routing while preserving the existing record stamping behavior. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-001` | Multiple queued edits are submitted in stable local creation order across reconnect and retry boundaries. | Preserves the only ordering guarantee declared by client/queue.py. |
| `AC-004` | `REQ-001` | `IMP-003` | `INV-001` | If connectivity fails after an apply but before acknowledgement, reconnect retry does not duplicate the logical edit and does not skip later queued edits. | Needed because no acknowledgement or idempotency contract currently exists. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-001` | blocked | The repository evidence does not define whether expired tombstones reject, defer, or permit late edits; choosing changes user-visible data semantics. | none | Product/feature owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Reconnect replay in client/queue.py | client/queue.py references offline.edits and local creation order. | verified target; implementation surface is currently only declarative constants |
| Record application and timestamping in models/record.py | models/record.py identifies offline.edits and updated_at. | verified target; executable write API is absent |
| Deletion conflict handling in server/tombstones.py | server/tombstones.py sets a 24-hour retention for offline.edits. | verified target; conflict behavior after expiry is absent |
| Tests for ordering, idempotency, timestamps, and tombstone expiry | No tests or test configuration are present in the repository. | verified by repository inventory |
| Graph paths for IMP-001 | PATH-002: client/queue.py → offline.edits | PATH-002: provider builtin; confidence lexical; location client/queue.py + server/tombstones.py |
| Graph paths for IMP-002 | PATH-001: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py |
| Graph paths for IMP-003 | PATH-001: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 40f38630d8a20355fa3b0dfe36988332; sha256 7e8a86aab3bde2682f0f22b7797a74401b1b6100985e4f9d287eeb625fe43baf; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-001` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Not ready |
