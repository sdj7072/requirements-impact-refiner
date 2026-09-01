# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | export.jobs retry policy changes from five attempts to unlimited attempts. | Permanently failing exports can remain active forever and may no longer reach terminal dead-letter handling through attempt exhaustion. | Export processing, dead-letter alerting, queue capacity, and operators investigating poison jobs. | Any export.jobs execution that fails on every attempt. | medium | The user explicitly accepts unlimited retry; preserve deterministic writes to make repeated attempts idempotent and retain separate operational cancellation or alerting if the runtime provides it. | accepted |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Retry export.jobs in workers/export.py forever. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Configure workers/export.py so export.jobs has no attempt limit and every failed attempt remains retryable indefinitely. Preserve the export.jobs identity and deterministic object key. Accept that attempt exhaustion will no longer send export.jobs failures to the dead_letter path consumed by alerts/dead_letter.py. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | The worker continues to handle the export.jobs job and write to its deterministic object key. | verified | workers/export.py defines JOB = "export.jobs" and OBJECT_KEY = "deterministic". |
| `INV-002` | alerts/dead_letter.py remains configured as a consumer of dead_letter and references export.jobs. | verified | alerts/dead_letter.py defines CONSUMES = "dead_letter" and JOB_REF = "export.jobs". |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | workers/export.py defines JOB = "export.jobs" and OBJECT_KEY = "deterministic". |
| `INV-002` | `REQ-001` | `IMP-001` | alerts/dead_letter.py defines CONSUMES = "dead_letter" and JOB_REF = "export.jobs". |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | functionality | medium | accepted | unknown | workers/export.py currently caps attempts at 5; the promoted graph receipt links alerts/dead_letter.py to export.jobs through PATH-001, but the receipt frontier says provider unavailable and the supplied files do not contain queue runtime code. | `INV-001`, `INV-002` | `DEC-001` | `AC-001`, `AC-002` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | Retry export.jobs forever with no terminal attempt limit. | `REQ-001` | `IMP-001` | The request states the exact mechanic—retry forever—so the loss of attempt-exhaustion dead-lettering is an accepted consequence rather than an unresolved choice. |

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
| new | `IMP-001` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | Configure workers/export.py so export.jobs has no attempt limit and every failed attempt remains retryable indefinitely. Preserve the export.jobs identity and deterministic object key. Accept that attempt exhaustion will no longer send export.jobs failures to the dead_letter path consumed by alerts/dead_letter.py. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | workers/export.py expresses an unlimited retry policy for export.jobs instead of MAX_ATTEMPTS = 5. | Directly test or inspect the worker configuration after the change. |
| `AC-002` | `REQ-001` | `IMP-001` | `INV-002` | The change does not rename export.jobs, change its deterministic object key, or alter alerts/dead_letter.py. | Compare workers/export.py and alerts/dead_letter.py after implementation. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| workers/export.py retry configuration | The requested behavior and current MAX_ATTEMPTS = 5 are both located in workers/export.py. | high |
| alerts/dead_letter.py downstream terminal-failure handling | The promoted scan identifies PATH-001 from alerts/dead_letter.py to export.jobs, and the file consumes dead_letter. | medium; the repository contains configuration constants but no runtime queue implementation. |
| Graph paths for IMP-001 | PATH-001: alerts/dead_letter.py → export.jobs | PATH-001: provider builtin; confidence lexical; location alerts/dead_letter.py + workers/export.py |
| Impact graph coverage | Impact scan: 0.0 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 2 nodes / 2 edges · 1 unknown frontiers | provider_limited; receipt 9d6c5d104ec0055d13f0050960b25d9d; sha256 2d3ace45dd6ecd4077b8040929da0e60b275197f02e1b284a46daab97d09009c; frontier FRONTIER-001 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `IMP-001`, `DEC-001` | `IMP-001` | `AC-001`, `AC-002` | Ready for implementation. Change only the export.jobs attempt-limit configuration, preserve job identity and deterministic object key, leave dead-letter consumer configuration untouched, and verify the unlimited sentinel expected by this repository. |
