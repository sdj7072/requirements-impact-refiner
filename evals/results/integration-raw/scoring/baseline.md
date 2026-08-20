# Task 4 — No-adapter integration baseline scoring

## Scope and scoring rule

Scored the four transcripts in `task4-baseline/` against the four `INT-*`
records in `evals/cases.json`.

- **D**: explicitly identifies the case's required entry or exit boundary.
- **P**: has a relevant sequencing signal, but does not name the required
  boundary/handoff precisely enough to be a stable routing contract.
- **M**: does not identify the required boundary.
- A must-not-do item is a **violation** only when the transcript actually
  performs the prohibited behavior. Ambiguous routing language is recorded
  separately; it is not counted as an invocation.

## Per-case result

| Case / transcript | Required entry | Required exit | Repeat broad clarification | Implementation plan / tasks | Automatic framework invocation | Wrong or multiple orchestrator | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `INT-generic` / `INT-generic.md` | **M** | **D** | No | No | No | No | Boundary failure |
| `INT-superpowers` / `INT-superpowers.md` | **D** | **P** | No | No | No | No | Routing ambiguity |
| `INT-claude-feature-dev` / `INT-claude-feature-dev.md` | **D** | **D** | No | No | No | No | Pass |
| `INT-spec-kit` / `INT-spec-kit.md` | **D** | **D** | No | No | No | No | Pass |

There are **0 confirmed must-not-do violations** across the four transcripts.
There is one missing entry-boundary detection and one non-exact exit/handoff,
so the no-adapter baseline does show routing ambiguity as Task 4 anticipated.

## Evidence and findings

### `INT-generic` — missing generic entry boundary

- **Entry: M.** The case requires entry after clarification (and Task 4's
  generic contract narrows that to a request concrete enough for repository
  inspection). The transcript enters a refinement report based only on
  approval status: “`REQ-001` — Refine the already-approved requirement into a
  planning-ready statement for the user’s own workflow” and then says “the
  approved requirement’s text, affected product area, and repository location
  were not supplied.” It never says clarification is complete, that the
  request is concrete enough to inspect, or that the refiner should wait for
  that entry condition. This is an early-entry ambiguity, not repeated broad
  clarification.
- **Exit: D.** It explicitly preserves user ownership: “for the user’s own
  workflow,” followed by “This refinement stops at a report-only handoff.”
  That is a framework-neutral handoff to the user's planning method.
- **Prohibitions: no violations.** “No work breakdown or implementation plan
  is created here, and no adapter or orchestration framework is referenced.”
  The transcript neither invokes a framework nor creates implementation tasks.

Exact excerpts and path:

- “Refine the already-approved requirement into a planning-ready statement for
  the user’s own workflow” —
  `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-baseline/INT-generic.md`
- “Scope is evidence-limited because the approved requirement’s text, affected
  product area, and repository location were not supplied in this integration
  request.” — same path
- “No work breakdown or implementation plan is created here, and no adapter or
  orchestration framework is referenced.” — same path

### `INT-superpowers` — exit is generic, not the exact `writing-plans` boundary

- **Entry: D.** The transcript grounds itself after the approved brainstorming
  outcome: “Implement the stakeholder-approved design from the brainstorming
  outcome” and “Brainstorming approved the design; refine repository impacts
  next.”
- **Exit: P.** It does not repeat brainstorming and it is clearly report-only,
  but it never names the required `writing-plans` boundary. Its exit is only:
  “Planning may proceed only after the pending inspection-boundary decision and
  evidence collection.” This is a generic planning transition, not an exact
  “exit before `writing-plans`” contract.
- **Prohibitions: no violations.** “This is a report-only baseline, not an
  implementation plan or work breakdown.” It recommends an inspection
  boundary, but does not call `writing-plans` or write tasks. No second or
  incorrect orchestrator is named.

Exact excerpts and path:

- “Implement the stakeholder-approved design from the brainstorming outcome” —
  `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-baseline/INT-superpowers.md`
- “Brainstorming approved the design; refine repository impacts next” — same
  path
- “Planning may proceed only after the pending inspection-boundary decision and
  evidence collection, or may explicitly carry the named gaps as blocked.” —
  same path

### `INT-claude-feature-dev` — exact Phase 3 to Phase 4 handoff

- **Entry: D.** “Analyze the change impact after feature-dev clarification has
  completed” and the verified invariant “feature-dev Phase 3 is complete”
  explicitly place refinement after Phase 3.
- **Exit: D.** “Feature-dev Phase 4 architecture has not started” preserves the
  pre-architecture boundary, and the stop check hands off rather than performs
  it: “The next workflow must record the selected handoff scope and begin
  architecture only with the clarified requirement as its baseline.”
- **Prohibitions: no violations.** The transcript does not repeat general
  clarification, author implementation tasks, or automatically invoke
  architecture. The architecture-first option is explicitly unselected: “No
  option was selected in the supplied request.” No other orchestrator appears.

Exact excerpts and path:

- “feature-dev Phase 3 is complete; feature-dev Phase 4 architecture has not
  started.” —
  `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-baseline/INT-claude-feature-dev.md`
- “The analysis stops at a report-only planning handoff.” — same path
- “The next workflow must record the selected handoff scope and begin
  architecture only with the clarified requirement as its baseline” — same
  path
- “No option was selected in the supplied request” — same path

### `INT-spec-kit` — exact clarification-to-plan boundary

- **Entry: D.** “Speckit clarify is complete” and “The clarification phase is
  complete before this refinement handoff” explicitly place refinement after
  clarification.
- **Exit: D.** The requirement states it must “not imply that `speckit.plan`
  has started,” and the stop check repeats the exact control point:
  “`speckit.plan` remains not started.” This is an explicit exit before the
  plan phase.
- **Prohibitions: no violations.** It does not repeat the specification,
  produce implementation tasks, or invoke `speckit.plan`; instead it says
  “This is a report-only handoff.” Only the Spec-Kit orchestrator is present.

Exact excerpts and path:

- “Speckit clarify is complete” —
  `/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-baseline/INT-spec-kit.md`
- “do not imply that `speckit.plan` has started.” — same path
- “`speckit.plan` remains not started.” — same path
- “This is a report-only handoff: it supplies the refined requirement,
  preserved baseline, impact evidence, open risks, pending decision, and
  acceptance criteria. It does not create a work breakdown or implementation
  plan.” — same path

## Routing-ambiguity summary

| Finding | Cases | Why it matters |
| --- | --- | --- |
| Missing exact generic entry gate | `INT-generic` | Approval alone is not the contract's concrete/clarified-for-inspection gate, so the refiner can start with no substantive requirement or scope. |
| Missing exact Superpowers exit | `INT-superpowers` | A generic “planning” handoff does not state ownership relative to `writing-plans`; this permits overlap or a second clarification/planning pass. |
| Repeated broad clarification | None | All four preserve the prior clarification state or ask only for evidence/authority gaps. |
| Implementation plan/tasks | None | Each transcript is report-only; none writes a work breakdown. |
| Automatic framework invocation | None confirmed | The feature-dev transcript proposes but does not select an architecture-first option; the others do not call their next framework step. |
| Wrong/multiple orchestrators | None | Each formal transcript stays in its named context; generic remains framework-neutral. |

## Conclusion

The baseline is safe on the hard prohibitions, but it is not yet a complete
routing contract. Adapter references should make the generic entry condition
and the Superpowers `writing-plans` exit explicit and mutually exclusive.
