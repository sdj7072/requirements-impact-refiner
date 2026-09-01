# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | The export.jobs retry policy changes from five attempts to no finite limit. | A permanently failing export can remain active indefinitely and consume repeated processing capacity. | Export workers and operators monitoring stuck export jobs. | export.jobs continues to fail after its fifth attempt. | medium | Represent unlimited retries explicitly and retain the deterministic object key so repeated processing targets the same export object. | accepted |
| `IMP-002` | export.jobs no longer exhausts retries into dead_letter. | Existing dead-letter alerts will no longer surface permanently failing export jobs. | The dead-letter alerting path and operators who relied on it for export failure visibility. | An export job fails continuously. | medium | Accept the loss of exhaustion-based dead-lettering for export.jobs while leaving alerts/dead_letter.py unchanged; monitor recurring failures through the worker's normal retry telemetry. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry export.jobs in workers/export.py forever. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Configure workers/export.py so export.jobs has no finite attempt limit and is retried indefinitely, while preserving its deterministic object key. Attempt exhaustion must no longer route export.jobs to dead_letter; other dead-letter behavior is outside scope. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | export.jobs continues to use the deterministic object key. | verified | workers/export.py defines JOB = "export.jobs" and OBJECT_KEY = "deterministic". |
| `INV-002` | The existing dead_letter consumer remains present and unchanged for any producers that still use it. | verified | alerts/dead_letter.py defines CONSUMES = "dead_letter"; the requested scope names only workers/export.py. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | workers/export.py defines JOB = "export.jobs" and OBJECT_KEY = "deterministic". |
| `INV-002` | `REQ-001` | `IMP-002` | alerts/dead_letter.py defines CONSUMES = "dead_letter"; the requested scope names only workers/export.py. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | medium | accepted | unknown | workers/export.py defines MAX_ATTEMPTS = 5 and the request replaces that cap; the promoted graph path was produced by a provider-unavailable fallback, so transitive runtime behavior is not verified. | `INV-001` | `DEC-001` | `AC-001`, `AC-002` |
| `IMP-002` | `REQ-001` | operations | medium | accepted | unknown | alerts/dead_letter.py consumes dead_letter and workers/export.py has a finite MAX_ATTEMPTS, but the mounted fixture does not contain the runtime transition code and the promoted graph used a fallback. | `INV-002` | `DEC-001` | `AC-003`, `AC-004` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Retry export.jobs indefinitely with no finite attempt-exhaustion transition. | `REQ-001` | `IMP-001`, `IMP-002` | The user explicitly requested retries forever; that exact mechanic necessarily accepts indefinite processing and removal of attempt-count-based dead-lettering for this job. |

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
| `REQ-001` | Configure workers/export.py so export.jobs has no finite attempt limit and is retried indefinitely, while preserving its deterministic object key. Attempt exhaustion must no longer route export.jobs to dead_letter; other dead-letter behavior is outside scope. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | workers/export.py represents export.jobs retries as unlimited rather than any finite integer attempt count. | Verify the retry configuration in workers/export.py and a direct assertion for its unlimited sentinel. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-001` | JOB remains export.jobs and OBJECT_KEY remains deterministic. | Direct assertions against workers/export.py constants. |
| `AC-003` | `REQ-001` | `IMP-002` | `INV-002` | No finite attempt count causes export.jobs to transition to dead_letter. | Assert the export retry limit uses the repository's unlimited sentinel. |
| `AC-004` | `REQ-001` | `IMP-002` | `INV-002` | alerts/dead_letter.py remains unchanged. | Compare alerts/dead_letter.py before and after the change. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| workers/export.py retry configuration for export.jobs | The file contains JOB, OBJECT_KEY, and MAX_ATTEMPTS constants. | high |
| alerts/dead_letter.py compatibility | The file consumes dead_letter and is linked to export.jobs by the promoted impact scan. | medium because runtime transition code is absent |
| Runtime retry-loop and telemetry implementation | No retry-loop or monitoring implementation exists in the mounted repository beyond the supplied constants. | low; verification is limited to configuration semantics |
| Graph paths for IMP-001 | PATH-001: alerts/dead_letter.py → export.jobs | PATH-001: provider builtin; confidence lexical; location alerts/dead_letter.py + workers/export.py |
| Graph paths for IMP-002 | PATH-001: alerts/dead_letter.py → export.jobs | PATH-001: provider builtin; confidence lexical; location alerts/dead_letter.py + workers/export.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 815a0dd774a771cf019d26ec3472443c; sha256 01810af55176d03c527915de8aa63d02844f47ea33268716c6483fd35bbe4f8c; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `IMP-002`, `DEC-001` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002`, `AC-003`, `AC-004` | Ready for implementation. Change only the export retry-limit configuration, preserve the deterministic key and job identity, leave the dead-letter consumer unchanged, and verify the unlimited sentinel directly. |
