# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | export.jobs retry policy changes from five attempts to unlimited retries. | Permanent failures will no longer reach the attempt-exhaustion dead-letter path consumed by alerts/dead_letter.py. | Dead-letter alerting for export.jobs. | export.jobs continues failing beyond five attempts. | medium | Treat the dead-letter bypass as an explicit consequence of the requested forever-retry policy and verify the configured attempt limit is removed. | accepted |
| `IMP-002` | Failures are retried without an attempt ceiling. | A permanently failing job can retry indefinitely and consume worker capacity or produce repeated failure logs. | Export worker operations and monitoring. | A non-transient export.jobs failure. | medium | Preserve the deterministic key and make the unlimited policy explicit so operations can distinguish it from accidental retry exhaustion. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry export.jobs in workers/export.py forever. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Change workers/export.py so export.jobs has no retry-attempt limit and is retried indefinitely after failures, while preserving its deterministic object key. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | export.jobs continues writing to the same deterministic object key across retry attempts. | verified | workers/export.py defines JOB = "export.jobs" and OBJECT_KEY = "deterministic". |
| `INV-002` | The worker continues to identify the job as export.jobs. | verified | workers/export.py defines JOB = "export.jobs". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-002` | workers/export.py defines JOB = "export.jobs" and OBJECT_KEY = "deterministic". |
| `INV-002` | `REQ-001` | `IMP-001` | workers/export.py defines JOB = "export.jobs". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | medium | accepted | unknown | The receipt links alerts/dead_letter.py to export.jobs in workers/export.py, but the exact runtime routing semantics are not present in this minimal repository. | `INV-002` | `DEC-001` | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | operations | medium | accepted | unknown | The repository does not expose scheduler semantics; generally, an unlimited retry policy can keep a permanently failing export.jobs item active indefinitely. | `INV-001` | `DEC-001` | `AC-003` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Retry export.jobs indefinitely with no maximum-attempt cutoff. | `REQ-001` | `IMP-001`, `IMP-002` | The user explicitly requested forever retries; this selects continued retry over the existing five-attempt dead-letter behavior. |

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
| `REQ-001` | Change workers/export.py so export.jobs has no retry-attempt limit and is retried indefinitely after failures, while preserving its deterministic object key. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | workers/export.py represents export.jobs retries as unlimited rather than capped at five attempts. | The current MAX_ATTEMPTS = 5 is the concrete limit to replace. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-002` | There is no attempt-count exhaustion for export.jobs that routes it to dead_letter. | alerts/dead_letter.py consumes dead_letter and references export.jobs, so unlimited retries intentionally bypass exhaustion-based delivery. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-001` | OBJECT_KEY remains deterministic after the retry-policy change. | workers/export.py currently defines OBJECT_KEY = "deterministic". |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| workers/export.py retry configuration for export.jobs | The file defines JOB, OBJECT_KEY, and MAX_ATTEMPTS. | verified |
| alerts/dead_letter.py behavior is not modified | The file only declares consumption of dead_letter and a reference to export.jobs. | verified |
| Graph paths for IMP-001 | PATH-001: alerts/dead_letter.py → export.jobs | PATH-001: provider builtin; confidence lexical; location alerts/dead_letter.py + workers/export.py |
| Graph paths for IMP-002 | PATH-001: alerts/dead_letter.py → export.jobs | PATH-001: provider builtin; confidence lexical; location alerts/dead_letter.py + workers/export.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 99fe17f213aa435ca588548b9ea0b938; sha256 2c44f0d4147a3e223a1915463bf9d7cb898ed2eaa4ddbcac0f8e851c6f28c6d0; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `IMP-002`, `DEC-001` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002`, `AC-003` | Ready for implementation. Replace the finite retry-attempt limit for export.jobs with the repository's unlimited-retry representation, preserve the deterministic object key, and verify the dead-letter consumer remains unchanged. |
