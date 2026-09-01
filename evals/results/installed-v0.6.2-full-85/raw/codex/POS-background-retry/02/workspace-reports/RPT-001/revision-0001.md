# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | export.jobs changes from five attempts to unlimited retries. | Dead-letter alerts for permanently failing export.jobs will no longer occur through retry exhaustion. | Operators and alerts/dead_letter.py behavior specific to export.jobs. | export.jobs continues failing after its fifth attempt. | medium | Accept loss of exhaustion-based export.jobs dead-letter alerts while retaining the existing consumer for other jobs. | accepted |
| `IMP-002` | export.jobs is retained for retry without an attempt ceiling. | A poison job may retry indefinitely and consume worker or queue resources. | Export workers, queue capacity, and operators. | A non-transient export.jobs failure never becomes successful. | medium | Keep retries idempotent at the deterministic object key and rely on existing external cancellation or operational controls if intervention is needed. | accepted |
| `IMP-003` | The number of possible writes to the export object becomes unbounded. | Retries could create duplicate export objects if the destination varied by attempt. | Export object storage and downstream readers. | export.jobs retries after a failed or ambiguous write. | low | Preserve the existing deterministic object key across every retry. | mitigated |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry export.jobs in workers/export.py forever. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | For export.jobs only, remove the five-attempt terminal limit in workers/export.py so every failed execution remains retryable indefinitely. Preserve the deterministic object key. Because export.jobs never exhausts retries, it must no longer reach the dead_letter path through attempt exhaustion; alerts/dead_letter.py remains unchanged for other dead-lettered work. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | Every retry of export.jobs writes to the same deterministic object key. | verified | workers/export.py defines JOB = "export.jobs" and OBJECT_KEY = "deterministic". |
| `INV-002` | The dead-letter alert consumer continues consuming dead_letter events for jobs that can still terminate there. | verified | alerts/dead_letter.py defines CONSUMES = "dead_letter"; the requested scope names only workers/export.py. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-002`, `IMP-003` | workers/export.py defines JOB = "export.jobs" and OBJECT_KEY = "deterministic". |
| `INV-002` | `REQ-001` | `IMP-001` | alerts/dead_letter.py defines CONSUMES = "dead_letter"; the requested scope names only workers/export.py. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | medium | accepted | unknown | workers/export.py currently caps MAX_ATTEMPTS at 5, while alerts/dead_letter.py references export.jobs; removing exhaustion implies this job no longer enters dead_letter because of repeated failure. The scan path used a provider-unavailable fallback, so the runtime transition is not directly verified. | `INV-002` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | operations | medium | accepted | unknown | An indefinitely failing job has no attempt-count terminal state, so it can continue consuming retry capacity until it succeeds or is externally cancelled. Runtime queue controls are not present in the supplied repository. | `INV-001` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | data | low | mitigated | unknown | workers/export.py defines OBJECT_KEY = "deterministic", indicating attempts target the same key rather than generating attempt-specific keys; runtime write behavior is not present in the supplied repository. | `INV-001` | none | `AC-002` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Remove the export.jobs attempt ceiling and retry indefinitely. | `REQ-001` | `IMP-001`, `IMP-002` | The user explicitly requested retrying export.jobs forever; this necessarily replaces attempt exhaustion and its export-specific dead-letter transition. |

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
| `REQ-001` | For export.jobs only, remove the five-attempt terminal limit in workers/export.py so every failed execution remains retryable indefinitely. Preserve the deterministic object key. Because export.jobs never exhausts retries, it must no longer reach the dead_letter path through attempt exhaustion; alerts/dead_letter.py remains unchanged for other dead-lettered work. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-002` | workers/export.py represents export.jobs with no finite maximum attempt count, and repeated failures beyond five attempts remain retryable rather than transitioning to dead_letter through exhaustion. | The current finite control is MAX_ATTEMPTS = 5; alerts/dead_letter.py is retained for other dead-letter events. |
| `AC-002` | `REQ-001` | `IMP-003` | `INV-001` | The unlimited-retry change leaves OBJECT_KEY = "deterministic" unchanged, including after more than five attempts. | workers/export.py currently declares the deterministic key independently of MAX_ATTEMPTS. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| workers/export.py retry-attempt policy for export.jobs | The file contains JOB = "export.jobs", OBJECT_KEY = "deterministic", and MAX_ATTEMPTS = 5. | verified |
| alerts/dead_letter.py remains unchanged, but export.jobs no longer reaches it by attempt exhaustion | The file consumes dead_letter and references export.jobs; the scan found a direct path between it and workers/export.py. | verified for references; transition behavior inferred from the supplied request and naming |
| Graph paths for IMP-001 | PATH-001: alerts/dead_letter.py → export.jobs | PATH-001: provider builtin; confidence lexical; location alerts/dead_letter.py + workers/export.py |
| Graph paths for IMP-002 | PATH-001: alerts/dead_letter.py → export.jobs | PATH-001: provider builtin; confidence lexical; location alerts/dead_letter.py + workers/export.py |
| Graph paths for IMP-003 | PATH-001: alerts/dead_letter.py → export.jobs | PATH-001: provider builtin; confidence lexical; location alerts/dead_letter.py + workers/export.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt fd4c137733a784139bf03f0790079fb5; sha256 d7662755c76a141a9983eb5ea2a75845dd4cfaa5a524b80d750024c18b35fa92; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `IMP-002`, `IMP-003`, `DEC-001` | `IMP-001`, `IMP-002` | `AC-001`, `AC-002` | Ready for implementation. Replace the finite export.jobs retry cap with the repository's representation of unlimited retries, preserve the deterministic object key, keep alerts/dead_letter.py unchanged, and verify the no-exhaustion and same-key criteria. |
