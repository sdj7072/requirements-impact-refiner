# Requirements Impact Report

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Speckit clarify is complete; refine impacts before planning. | Supplied `INT-spec-kit` evaluation state |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | Consume the already-clarified Spec Kit requirement and its current Planning Handoff, preserve that artifact as the baseline, refine material impacts with repository evidence, and return the canonical impact report before `speckit.plan`. Do not repeat general clarification, invoke the external workflow, or create planning tasks. The authoritative clarification artifact and feature mechanics remain the pending decision/evidence gap. | the pending decision | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `speckit.clarify` is complete and its resulting requirement is the baseline entering this refinement. | `verified` | Supplied task state: “Speckit clarify is complete”; Spec Kit adapter `Entry`/`Ownership`. |
| `INV-002` | `speckit.plan` has not started; this report is the handoff boundary before planning. | `verified` | Supplied task state: “speckit.plan not started”; Spec Kit adapter `Exit`. |
| `INV-003` | The clarified requirement, decisions, and Planning Handoff must be carried forward rather than re-specified here. | `verified` | `integration-spec-kit.md` — `Ownership` and `Output` require consuming and preserving the resulting requirement. |
| `INV-004` | No concrete feature transition, data, compatibility, authorization, retry, or operational policy is selected in the supplied evidence. | `unknown` | No clarified requirement artifact or stakeholder mechanics selection is supplied in scope. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | Completed clarification is the selected Spec Kit entry state. |
| `INV-002` | `REQ-001` | `IMP-003` | Planning remains unstarted and is the downstream boundary. |
| `INV-003` | `REQ-001` | `IMP-001`, `IMP-002` | Adapter requires the clarified requirement and handoff to remain authoritative. |
| `INV-004` | `REQ-001` | `IMP-004` | No explicit mechanics decision is present; silence cannot be treated as acceptance. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | Workflow / Compatibility | high | `refining` | `verified` | Without carrying the completed clarification artifact into this handoff, later planning can diverge from its decisions; the adapter requires consuming that requirement. | `INV-001`, `INV-003` | the pending decision | `AC-001` |
| `IMP-002` | `REQ-001` | Functionality / Data / Interfaces / Authorization / State / Operations / Compatibility / Legal / Regression | high | `blocked` | `unknown` | Phase status alone does not expose feature behavior, schemas, contracts, permissions, concurrency, operations, policy, or tests; the clarified requirement and repository evidence are not supplied. | `INV-003` | the pending decision | `AC-002` |
| `IMP-003` | `REQ-001` | Workflow / Regression | high | `refining` | `inferred` | Invoking `speckit.plan` before this report would turn unexamined impacts into planning assumptions; the adapter exits before that workflow. | `INV-002` | the pending decision | `AC-003` |
| `IMP-004` | `REQ-001` | Decision governance | medium | `blocked` | `verified` | A concrete mechanics choice cannot be recorded without an explicit stakeholder selection; the evidence model forbids silent acceptance and no selection is supplied. | `INV-004` | the pending decision | `AC-004` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| None | No user/stakeholder policy choice is recorded. The authoritative clarified artifact and any feature mechanics remain the pending decision. | `REQ-001` | None | The supplied phase state fixes the integration boundary but does not select product or implementation policy. No impact is silently accepted. |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Delta |
| --- | --- | --- | --- | --- |
| `REQ-001` | Added the Spec Kit entry after `speckit.clarify`, preservation of its requirement and Planning Handoff, evidence-based refinement, and report-only exit before `speckit.plan`. | the pending decision | — | Clarified workflow ownership; no implementation plan or planning tasks created. |

## Focused Decision

One evidence-gap question remains: which artifact is the authoritative completed `speckit.clarify` requirement for this refinement and later planning handoff?

1. The completed `speckit.clarify` output (recommended): identify it by path or stable artifact ID and preserve its decisions as the source of truth.
2. A separately supplied requirement/specification artifact: use it only after explicitly establishing its relationship to the completed clarification.
3. Proceed with phase-state-only refinement: carry the missing requirement and feature evidence as blocked gaps.

No concrete decision ID is recorded because no option was selected.

## Whole-Set Recalculation

No decision was supplied. The complete known impact set remains `IMP-001` through `IMP-004`; no impact is accepted or resolved by silence. The two refining impacts remain open, and the two blocked impacts remain blocked pending named evidence.

### Delta

- resolved: none
- mitigated: none
- unchanged: `IMP-001`, `IMP-003`
- accepted: none
- deferred: none
- blocked: `IMP-002`, `IMP-004`
- new: none

Each known impact appears exactly once in the delta categories.

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001`, `INV-003` | The handoff identifies and preserves the completed clarification requirement and Planning Handoff without reopening general clarification. | Verify the selected clarification artifact is carried into the report and compare its decisions with the report baseline; artifact identity is currently missing. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-003` | Every material product impact is classified with repository or supplied-artifact evidence; unsupported categories remain explicitly unknown or blocked. | Inspect the identified clarification artifact, relevant repository paths, contracts, schemas, policies, and tests; none are supplied in this evaluation. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-002` | The canonical report is handed off before any `speckit.plan` invocation or planning task is created. | Confirm the downstream Spec Kit state remains not started at handoff. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-004` | Any selected transition or policy mechanics are traceable to an explicit stakeholder choice; absent that choice, the impact remains blocked. | Record an explicit choice in the owning workflow before assigning a concrete decision ID. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |
| `IMP-002` | `blocked` | The clarified requirement, repository behavior, contracts, data, permissions, operations, policy, and regression inventory are not supplied. | the pending decision | Spec Kit owner, after providing the clarification artifact and repository scope |
| `IMP-004` | `blocked` | No stakeholder selection of feature mechanics or policy is supplied. | the pending decision | Requirement owner |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Integration boundary only; no feature-specific clarified requirement or product repository evidence was supplied. | Supplied `INT-spec-kit` phase state; `integration-spec-kit.md`; core evidence, taxonomy, and refinement-loop guidance. | Workflow entry/exit claims are verified, but feature-specific impacts remain unknown or blocked. |
| This report is a report-only handoff and does not invoke an external workflow. | `integration-spec-kit.md` — `Ownership`, `Output`, and `Exit`. | Planning must begin only after the owning Spec Kit workflow receives and reviews this report. |

## Stop Check and Planning Handoff

The integration-level boundary is refined, but feature-specific material impacts cannot be resolved without the named clarification artifact and repository evidence. This report stops before `speckit.plan`; it creates no implementation work breakdown or planning tasks. `IMP-002` and `IMP-004` remain explicitly blocked, while `IMP-001` and `IMP-003` remain open and unchanged pending the focused decision/evidence.

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001`: consume the completed `speckit.clarify` requirement, refine evidence-backed impacts, and hand off before `speckit.plan` without repeating clarification. | `REQ-001`, `INV-001`–`INV-004`, `IMP-001`–`IMP-004` | Missing authoritative clarification artifact; feature behavior, contracts, data, authorization, concurrency, operations, policy, and regression evidence; no explicit mechanics selection. | `AC-001`–`AC-004` | Spec Kit; report-only handoff before `speckit.plan`. |
