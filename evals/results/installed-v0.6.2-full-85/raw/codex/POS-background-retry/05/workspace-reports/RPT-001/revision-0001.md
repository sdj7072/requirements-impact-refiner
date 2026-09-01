# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | export.jobs retry exhaustion | A permanently failing export job will never exhaust attempts or be routed to dead_letter by the attempt ceiling. | The export worker and dead-letter alerting path for export.jobs. | Any export.jobs execution that continues to fail after five or more attempts. | medium | Represent the retry limit as unbounded only for export.jobs, while preserving its deterministic object key and documenting the accepted loss of attempt-exhaustion dead-lettering. | accepted |
| `IMP-002` | export.jobs retry duration | Poison jobs may retry indefinitely and consume worker or queue capacity. | Export worker operations and queue throughput. | A non-recoverable export failure. | medium | Accept the ongoing retry behavior requested here and retain deterministic output identity; operational backoff or monitoring is outside the evidenced scope. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry export.jobs in workers/export.py forever. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | For the export.jobs worker, remove the finite five-attempt ceiling so failed jobs remain retryable indefinitely. Preserve the existing deterministic object key and leave the dead-letter consumer unchanged; export.jobs must no longer reach dead_letter because of retry-attempt exhaustion. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | export.jobs writes continue to use the existing deterministic object key. | verified | workers/export.py defines OBJECT_KEY = "deterministic". |
| `INV-002` | The worker continues to identify the job as export.jobs. | verified | workers/export.py defines JOB = "export.jobs". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | workers/export.py defines OBJECT_KEY = "deterministic". |
| `INV-002` | `REQ-001` | `IMP-001` | workers/export.py defines JOB = "export.jobs". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | medium | accepted | unknown | workers/export.py verifies MAX_ATTEMPTS = 5. The receipt textually and structurally infers a path through export.jobs to alerts/dead_letter.py, but ast-grep, codegraph, and SCIP providers were unavailable, so the transitive dead-letter consequence remains graph-unknown. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | operations | medium | accepted | unknown | Removing a finite retry ceiling can let a permanently failing export.jobs item continue consuming retry capacity indefinitely, but no queue scheduling or backoff implementation is present in the supplied repository scope. | `INV-001` | `DEC-001` | `AC-001` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Retry export.jobs forever with no finite maximum attempt count. | `REQ-001` | `IMP-001`, `IMP-002` | The user explicitly requested indefinite retries, so the resulting lack of retry-exhaustion dead-lettering and possible persistent-failure load are accepted consequences rather than open choices. |

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
| new | `IMP-001`, `IMP-002` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | For the export.jobs worker, remove the finite five-attempt ceiling so failed jobs remain retryable indefinitely. Preserve the existing deterministic object key and leave the dead-letter consumer unchanged; export.jobs must no longer reach dead_letter because of retry-attempt exhaustion. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | workers/export.py configures MAX_ATTEMPTS as unbounded rather than a finite integer, and export.jobs therefore has no attempt-count exhaustion point. | The current finite control is the single constant MAX_ATTEMPTS = 5 in workers/export.py. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | workers/export.py retains OBJECT_KEY = "deterministic" unchanged. | The deterministic key is current verified behavior and makes repeated export writes target the same object identity. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| workers/export.py retry-attempt configuration for export.jobs | The file defines JOB, OBJECT_KEY, and MAX_ATTEMPTS; MAX_ATTEMPTS is the requested behavior-control point. | high |
| alerts/dead_letter.py remains unchanged | The file consumes dead_letter and references export.jobs, while the requested scope names workers/export.py. | high for file contents; graph relation unknown because providers were unavailable |
| Queue backoff, scheduling, and monitoring behavior | No implementation or configuration for those concerns exists in the repository evidence or scanned files. | unknown and out of current implementation scope |
| Graph paths for IMP-001 | PATH-001: alerts/dead_letter.py → export.jobs | PATH-001: provider builtin; confidence lexical; location alerts/dead_letter.py + workers/export.py |
| Graph paths for IMP-002 | This operational consequence is supplied-only because the repository contains only the worker constants and dead-letter reference, with no queue/backoff implementation to trace; provider coverage was unavailable, so confidence remains unknown. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 4ced7f2f1c688f69e54e02c5ab88be05; sha256 1780775da64aa0a6c7fd75b2e147c603251e5f93e59339424cab09d21f874f7c; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `IMP-002`, `DEC-001` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002` | Ready for implementation: change only the export.jobs attempt limit in workers/export.py, preserve the deterministic object key and job name, and verify the resulting constants plus any available tests. Remaining accepted risk: provider-unverified dead-letter linkage and possible indefinite poison-job load. |
