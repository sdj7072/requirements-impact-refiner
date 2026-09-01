# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | export.jobs changes from five attempts to unlimited retries. | Attempt-exhausted export jobs will no longer reach the dead-letter alert path. | Operators and alerting that rely on alerts/dead_letter.py for failed export jobs. | An export job fails repeatedly beyond the former fifth attempt. | medium | Accept the loss of attempt-exhaustion alerts as an explicit consequence of retrying forever; retain the dead-letter consumer for other traffic. | accepted |
| `IMP-002` | The retry policy no longer terminates after a bounded number of failures. | A poison export job can retry indefinitely and consume operational capacity. | Worker throughput, queue depth, and operators diagnosing persistent failures. | A non-transient export failure persists across retries. | high | Keep the scope limited to export.jobs and preserve the deterministic key; accept ongoing retry load as part of the explicit forever-retry choice. | accepted |
| `IMP-003` | The same export operation may execute an unbounded number of times. | Repeated attempts can rewrite the destination object. | Consumers of the deterministic export object. | A retry occurs after a partial or externally visible write. | low | Preserve the deterministic object key so retries do not fan out into multiple object keys. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry export.jobs in workers/export.py forever. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Configure workers/export.py so export.jobs has no attempt limit and is retried indefinitely. Preserve its deterministic object key. Attempt exhaustion must no longer route export.jobs to dead_letter; alerts/dead_letter.py remains unchanged for any other dead-letter traffic. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The worker continues to identify the job as export.jobs. | verified | workers/export.py defines JOB = "export.jobs". |
| `INV-002` | Exports continue to use the deterministic object key. | verified | workers/export.py defines OBJECT_KEY = "deterministic". |
| `INV-003` | The dead-letter alert consumer remains available and continues to reference export.jobs. | verified | alerts/dead_letter.py defines CONSUMES = "dead_letter" and JOB_REF = "export.jobs". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-002` | workers/export.py defines JOB = "export.jobs". |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-003` | workers/export.py defines OBJECT_KEY = "deterministic". |
| `INV-003` | `REQ-001` | `IMP-001` | alerts/dead_letter.py defines CONSUMES = "dead_letter" and JOB_REF = "export.jobs". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | medium | accepted | unknown | The scan found a lexical/structural relationship from alerts/dead_letter.py to export.jobs, but no runtime routing implementation is present. | `INV-001`, `INV-003` | `DEC-001` | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | operations | high | accepted | unknown | No scheduler, retry delay, or queue-capacity implementation is present in the supplied repository, so the runtime load effect cannot be verified here. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-003` |
| `IMP-003` | `REQ-001` | data | low | mitigated | unknown | The file verifies a deterministic object-key configuration, but no object-store implementation is present to verify runtime write semantics. | `INV-002` | none | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Retry export.jobs indefinitely with no maximum attempt count. | `REQ-001` | `IMP-001`, `IMP-002` | The user explicitly requested retrying forever, so the resulting loss of attempt-exhaustion dead-lettering and persistent retry load are selected tradeoffs. |

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
| `REQ-001` | Configure workers/export.py so export.jobs has no attempt limit and is retried indefinitely. Preserve its deterministic object key. Attempt exhaustion must no longer route export.jobs to dead_letter; alerts/dead_letter.py remains unchanged for any other dead-letter traffic. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-002` | `INV-001` | workers/export.py represents MAX_ATTEMPTS as unlimited rather than 5. | The requested policy is forever; the current file sets MAX_ATTEMPTS = 5. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-003` | export.jobs cannot exhaust attempts solely because of a retry count, while alerts/dead_letter.py remains unchanged. | The dead-letter consumer currently references export.jobs and attempt exhaustion is the behavior being removed. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-002` | OBJECT_KEY remains deterministic after the retry-policy change. | workers/export.py identifies the deterministic key as existing behavior. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| workers/export.py retry configuration for export.jobs | The file defines JOB, OBJECT_KEY, and MAX_ATTEMPTS. | verified |
| alerts/dead_letter.py integration consequence | The file consumes dead_letter and references export.jobs. | verified |
| Queue backoff, cancellation, and worker scheduling behavior | No queue framework or scheduler implementation is present in the repository snapshot. | unknown and out of scope |
| Graph paths for IMP-001 | PATH-001: alerts/dead_letter.py → export.jobs | PATH-001: provider builtin; confidence lexical; location alerts/dead_letter.py + workers/export.py |
| Graph paths for IMP-002 | The promoted receipt contains only the alerts/dead_letter.py to workers/export.py relationship; scheduler and queue behavior are absent. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-003 | The receipt has no object-store path; runtime rewrite behavior remains unknown. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 9ca8b8d5a369271e8e2cb0a194957ea6; sha256 09abd01074f9a8602004882735b7f275d9768a25af87d21fe60999ce9bb36d85; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002`, `AC-003` | Ready for implementation. Set the attempt policy to unlimited in workers/export.py, preserve the job and object-key constants, leave alerts/dead_letter.py unchanged, and verify the resulting configuration. |
