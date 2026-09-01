# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | pre-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | Reconnect synchronization replays offline.edits through models/record.py. | Edits may be skipped, duplicated, reordered, or bypass normal updated_at stamping during reconnect. | Clients reconnecting with one or more queued offline edits. | Connectivity returns while client/queue.py contains offline.edits. | high | Drain a stable queue snapshot exactly once in local creation order and invoke the record-processing entry point for every edit before acknowledging/removing it. | refining |
| `IMP-002` | Reconnect synchronization may replay edits created while a record was deleted on the server. | After the 24-hour tombstone expires, replay cannot reliably distinguish an update from unintended resurrection of a deleted record. | Offline clients reconnecting more than 24 hours after a server-side deletion. | A queued edit targets a record whose deletion tombstone is no longer retained. | critical | Select and test an explicit stale-delete conflict policy before enabling automatic replay. | blocked |
| `IMP-003` | Offline edits receive updated_at values during reconnect replay. | Replay-time timestamps can make old offline changes appear newer than intervening server changes, causing last-write-wins conflicts. | Records edited both offline and on the server before reconnect. | A queued offline edit and a server-side mutation affect the same record. | high | Keep deterministic queue order and define conflict comparison using explicit edit metadata or a documented replay policy rather than assuming updated_at reflects original edit time. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Sync offline.edits through models/record.py when the app reconnects. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | When the application reconnects, replay queued offline.edits in preserved local creation order through the models/record.py record-processing path so each edit receives the normal updated_at handling; define safe behavior for an edit whose corresponding server deletion tombstone has already expired after 24 hours. | — | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | offline.edits processed by models/record.py are stamped with updated_at. | verified | models/record.py declares STREAM = "offline.edits" and STAMPED = "updated_at". |
| `INV-002` | The client queue preserves only local edit creation order. | verified | client/queue.py declares PRESERVES = "local creation order only" for offline.edits. |
| `INV-003` | Server deletion tombstones for offline.edits are retained for 24 hours. | verified | server/tombstones.py declares TOMBSTONE_HOURS = 24 and STREAM_REF = "offline.edits". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | models/record.py declares STREAM = "offline.edits" and STAMPED = "updated_at". |
| `INV-002` | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003` | client/queue.py declares PRESERVES = "local creation order only" for offline.edits. |
| `INV-003` | `REQ-001` | `IMP-002`, `IMP-003` | server/tombstones.py declares TOMBSTONE_HOURS = 24 and STREAM_REF = "offline.edits". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | high | refining | unknown | The compact graph includes PATH-001 between client/queue.py and models/record.py, but provider fallback leaves the semantic call relationship unverified. | `INV-001`, `INV-002` | the pending decision | `AC-001`, `AC-002`, `AC-003` |
| `IMP-002` | `REQ-001` | data | critical | blocked | unknown | The compact graph includes PATH-002 between client/queue.py and server/tombstones.py, but provider fallback leaves post-expiry replay semantics unverified. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-004` |
| `IMP-003` | `REQ-001` | state/concurrency | high | refining | unknown | The compact graph includes PATH-001 and PATH-002, but no verified conflict chronology or resolution rule exists in the supplied files. | `INV-001`, `INV-002`, `INV-003` | the pending decision | `AC-002`, `AC-005` |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| What should reconnect sync do when a queued offline edit targets a record whose server tombstone has expired? | Reject the edit and surface a sync conflict | `IMP-002`, `IMP-003` | Safest against silent data resurrection, but requires a visible conflict/recovery path for the user. |
| What should reconnect sync do when a queued offline edit targets a record whose server tombstone has expired? | Apply the edit and recreate the record | `IMP-002`, `IMP-003` | Maximizes automatic recovery of offline work, but may silently resurrect records intentionally deleted on the server. |
| What should reconnect sync do when a queued offline edit targets a record whose server tombstone has expired? | Pause replay and require manual resolution | `IMP-002`, `IMP-003` | Avoids automatic data loss or resurrection, but blocks the remaining queue until a resolver acts. |

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
| `REQ-001` | When the application reconnects, replay queued offline.edits in preserved local creation order through the models/record.py record-processing path so each edit receives the normal updated_at handling; define safe behavior for an edit whose corresponding server deletion tombstone has already expired after 24 hours. | the pending decision | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | On reconnect, each edit in the captured offline.edits queue is processed exactly once and removed only after successful processing. | Required to prevent loss or duplication while draining client/queue.py. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-002` | Replay invokes models/record.py in the same local creation order preserved by client/queue.py. | client/queue.py guarantees only local creation order. |
| `AC-003` | `REQ-001` | `IMP-001` | `INV-001` | Every replayed offline edit goes through the record-processing path and receives updated_at there. | models/record.py is the verified updated_at stamping boundary. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-003` | A reconnect occurring after the 24-hour tombstone window follows the selected explicit conflict policy and has a regression test. | server/tombstones.py retains tombstones for only 24 hours. |
| `AC-005` | `REQ-001` | `IMP-003` | `INV-001` | Concurrent server mutations and queued offline edits resolve deterministically without treating replay-time updated_at as proof of original edit chronology. | The supplied files verify replay-time stamping and local queue order, but no original edit timestamp or conflict rule. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-002` | blocked | The repository evidence does not define whether an edit after tombstone expiry should be rejected, recreated, or manually resolved. | none | Product/data owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Reconnect queue draining in client/queue.py | client/queue.py is the supplied offline.edits queue boundary. | high |
| Record processing and updated_at stamping in models/record.py | models/record.py is the supplied normal processing path. | high |
| 24-hour delete retention and expired-tombstone handling in server/tombstones.py | server/tombstones.py defines the retention window; post-expiry semantics are absent. | high for retention, unknown for behavior after expiry |
| Graph paths for IMP-001 | PATH-001: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py |
| Graph paths for IMP-002 | PATH-002: client/queue.py → offline.edits | PATH-002: provider builtin; confidence lexical; location client/queue.py + server/tombstones.py |
| Graph paths for IMP-003 | PATH-001: client/queue.py → offline.edits &#124;&#124; PATH-002: client/queue.py → offline.edits | PATH-001: provider builtin; confidence lexical; location client/queue.py + models/record.py &#124;&#124; PATH-002: provider builtin; confidence lexical; location client/queue.py + server/tombstones.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 3 nodes / 6 edges · 1 unknown frontiers | provider_limited; receipt 05d26a623694c5ce62dd9c8dc809b183; sha256 d85ff21797f87a44ab702e136338c9c03d1b5f549933a7d1ba995db82eaf9639; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003` | `IMP-002` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005` | Not ready |
