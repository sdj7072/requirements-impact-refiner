# Requirements Impact Report

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Brainstorming approved the design; refine repository impacts next. The approved Task 4 design adds optional, mutually exclusive workflow adapters while preserving report-only ownership. | `evals/cases.json` — `INT-superpowers`; `docs/superpowers/specs/2026-08-20-requirements-impact-refiner-design.md` — §§8.1–8.3 |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | After `brainstorming` design approval, inspect repository evidence using only the selected Superpowers adapter; ask only evidence-gap or impact-resolution questions; return the canonical impact report and `Planning Handoff`; exit before `writing-plans` without invoking it or creating implementation tasks. | the pending decision | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `SKILL.md` routes a known `superpowers` mode to exactly one adapter and forbids loading multiple adapters or invoking an external workflow. | verified | `skills/requirements-impact-refiner/SKILL.md:25–34` |
| `INV-002` | The Superpowers adapter treats approved brainstorming as its entry, preserves the approved design as baseline, and emits a canonical report rather than an implementation plan. | verified | `skills/requirements-impact-refiner/references/integration-superpowers.md:3–17` |
| `INV-003` | Adapter contract tests require the exact Superpowers entry/exit phrases, canonical `Planning Handoff`, and no implementation plan. | verified | `tests/test_integration_adapters.py:17–21,59–73` |
| `INV-004` | The no-adapter baseline had no confirmed prohibited action, but Superpowers had only a generic planning exit rather than an explicit `writing-plans` boundary. | verified | `.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-baseline-scoring.md:18–27,61–75` |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001`, `IMP-004` | `SKILL.md:25–34` |
| `INV-002` | `REQ-001` | `IMP-002`, `IMP-003` | `integration-superpowers.md:5–17` |
| `INV-003` | `REQ-001` | `IMP-001`, `IMP-002` | `tests/test_integration_adapters.py:46–86` |
| `INV-004` | `REQ-001` | `IMP-003` | `task4-baseline-scoring.md:61–75` |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Interfaces / compatibility | high | mitigated | verified | Routing table names exactly one adapter per selected mode; adapter tests enforce the Superpowers boundary. `SKILL.md:27–34`; `tests/test_integration_adapters.py:75–82` | `INV-001`, `INV-003` | — | `AC-001` |
| `IMP-002` | `REQ-001` | Regression / workflow ownership | high | mitigated | verified | Adapter explicitly says not to repeat clarification, asks only evidence-gap or impact-resolution questions, and does not invoke the external workflow. `integration-superpowers.md:7–13` | `INV-002`, `INV-003` | — | `AC-002` |
| `IMP-003` | `REQ-001` | Operations / regression validation | high | blocked | unknown | The committed adapter tests validate document contracts, but the required five-repetition `INT-superpowers` evaluation corpus is not supplied for this fresh run. Task 4's report explicitly requires the controller to run it before updating results. `.superpowers/sdd/2026-08-20-requirements-impact-refiner/task-4-report.md:1–3,31–36` | `INV-002`, `INV-004` | — | `AC-003` |
| `IMP-004` | `REQ-001` | Compatibility / orchestration | medium | detected | inferred | Static repository contracts prevent duplicate adapter routing, but runtime client behavior and simultaneous-orchestrator detection are not proven by the adapter unit tests. `SKILL.md:27`; `tests/test_integration_adapters.py:75–82` | `INV-001` | — | `AC-004` |

## Decision needed

Should this Task 4 handoff treat the missing five-repetition integration evaluation as a blocking prerequisite, or hand it to `writing-plans` with the evaluation gap explicitly carried forward?

- Run the five repetitions first and update the evaluation corpus (clears the evidence gap before planning).
- Carry the gap as `blocked` into planning (keeps the report handoff now, but does not claim runtime validation).

No stakeholder selection has been recorded; therefore no concrete `DEC-###` is created and no risk is silently accepted.

## Recorded decision

None. The pending decision is not a recorded user choice.

## Whole-set recalculation

The approved brainstorming design changes the routing contract, not the product behavior being designed. Rechecking all known impacts leaves the adapter-contract risks mitigated, preserves the missing-runtime-evaluation gap, and leaves simultaneous-orchestrator behavior as an evidence-limited concern. No impact is superseded and no new impact was identified.

## Delta

- resolved: none
- mitigated: `IMP-001`, `IMP-002`
- unchanged: `IMP-004`
- accepted: none
- deferred: none
- blocked: `IMP-003`
- new: none

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001`, `INV-003` | With `superpowers` selected, exactly `integration-superpowers.md` is loaded; its entry is after brainstorming approval and its exit is before `writing-plans`. | `tests/test_integration_adapters.py:59–65,75–82` |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | The report does not reopen brainstorming, invoke `writing-plans`, or author implementation tasks; any question is limited to an evidence gap or impact resolution. | `integration-superpowers.md:7–17`; `evals/cases.json` — `INT-superpowers` must-not-do clauses |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-004` | Five fresh repetitions of `INT-superpowers` record exact entry/exit boundaries, no broad clarification repetition, no automatic framework invocation, no implementation tasks, and no multiple orchestrators. | Validation gap: required fresh corpus not yet available; see `task-4-report.md:31–36` |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-001` | If more than one orchestrator is active, the run asks the user to choose one before continuing; no second adapter is loaded. | `integration-superpowers.md:7–9`; runtime multi-orchestrator evaluation remains unverified |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-003` | blocked | Fresh five-repetition Superpowers integration transcripts and scoring are absent. | the pending decision | evaluation controller |
| `IMP-004` | detected | Static contract tests cannot establish runtime client routing or multi-orchestrator detection. | the pending decision | planning workflow / evaluator |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Inspected the approved design, Task 4 brief/report, core skill, selected Superpowers adapter, adapter tests, case contract, and baseline scoring. | Repository paths cited above. | Adapter contract and boundaries are verified. |
| No external workflow was invoked and no implementation plan was authored. | `integration-superpowers.md:11–17`; approved design §2. | This is a report-only handoff, as required; planning ownership remains outside this report. |
| Fresh runtime repetition corpus is unavailable. | `task-4-report.md:1–3,31–36`. | Runtime non-overlap and client-specific behavior remain unknown/blocked; do not claim evaluation pass. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `INV-001`–`INV-004`, `IMP-001`–`IMP-004` | `IMP-003` is blocked pending five fresh repetitions; `IMP-004` remains runtime-inferred. No risk is accepted by silence. | `AC-001`–`AC-004` | Superpowers `writing-plans`, only after this report exits; this artifact does not invoke it or create its work breakdown. |

## Stop Check

The report stops before `writing-plans` as required by the selected adapter. Contract impacts are mitigated with direct repository evidence; the missing evaluation is named and blocked; the remaining runtime concern is disclosed. No implementation tasks or plan are included.
