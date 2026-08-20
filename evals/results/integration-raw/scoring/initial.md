# Task 4 green-corpus scoring

## Scope and method

Strictly scored the 30-run corpus in
`/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-green/`
against the corresponding `INT-*`, `NEG-brainstorming`, and `NEG-planning`
records in `evals/cases.json`, the current entrypoint, and exactly the four
integration references.

Scoring notation:

- **D** — exact required boundary is stated.
- **P** — relevant sequencing signal, but not an exact/stable boundary.
- **M** — required boundary is not identified.
- **Pass** requires all applicable required boundaries and no prohibited action.
- A named next workflow is not an automatic invocation when the transcript
  explicitly leaves it unstarted. An unselected option is likewise not an
  invocation.

For generic mode, the required entry is *after clarification / when concrete
enough for repository inspection*; approval alone is insufficient. The
generic exit is a handoff to the user's selected planning method without
starting it.

## INT-generic (5 runs)

| Run | Entry | Exit | Two orchestrators | Broad ideation repeat | Implementation tasks | Automatic framework invocation | Unselected-framework mention | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `INT-generic-1` | **M** | D | No | No | No | No | No | Fail — entry |
| `INT-generic-2` | **M** | D | No | No | No | No | No | Fail — entry |
| `INT-generic-3` | **M** | D | No | No | No | No | No | Fail — entry |
| `INT-generic-4` | **M** | D | No | No | No | No | No | Fail — entry |
| `INT-generic-5` | **M** | D | No | No | No | No | No | Fail — entry |

### INT-generic misses

All five runs begin refinement from approval/before-planning language despite
admitting that the substantive requirement and repository scope are absent.
None states that clarification is complete or that the request is concrete
enough to inspect. These are **M**, not merely P, under the baseline scoring
rule: the necessary entry condition itself is omitted.

- `INT-generic-1`, lines 6 and 9: “**Entry:** The request says the requirement
  is approved and asks for repository-impact refinement before planning” and
  “No approved requirement text, repository paths, diff, tests, schema, or
  contract were supplied in this handoff.”
  [`INT-generic-1.md`](/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-green/INT-generic-1.md:6)
- `INT-generic-2`, lines 7–9: “Refine this approved requirement before I plan
  it with my own workflow” and “its substantive text is not supplied.”
  [`INT-generic-2.md`](/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-green/INT-generic-2.md:7)
- `INT-generic-3`, lines 5–7: “Refine the approved requirement … then hand
  the resulting report to the user’s own planning workflow”; supplied evidence
  is only approval and no active named orchestrator.
  [`INT-generic-3.md`](/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-green/INT-generic-3.md:5)
- `INT-generic-4`, lines 5–7: “Refine the already-approved requirement” while
  stating that “The substantive requirement text and product repository scope
  are not supplied.”
  [`INT-generic-4.md`](/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-green/INT-generic-4.md:5)
- `INT-generic-5`, lines 7 and 19: the run treats approval as sufficient:
  “the requirement is approved” and “already approved and is being refined
  before planning,” without a clarification/completeness gate.
  [`INT-generic-5.md`](/Users/p042890/Documents/Codex/2026-08-12/new-chat-3/.worktrees/requirements-impact-refiner/.superpowers/sdd/2026-08-20-requirements-impact-refiner/task4-green/INT-generic-5.md:7)

Each generic exit is exact. For example, run 1 says “handed to the user’s
chosen planning method” and “does not start that method automatically” at
line 61; the other four preserve the same user-owned, framework-neutral
handoff.

## INT-superpowers (5 runs)

| Run | Entry | Exit | Two orchestrators | Broad ideation repeat | Implementation tasks | Automatic `writing-plans` invocation | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `INT-superpowers-1` | D | D | No | No | No | No | Pass |
| `INT-superpowers-2` | D | D | No | No | No | No | Pass |
| `INT-superpowers-3` | D | D | No | No | No | No | Pass |
| `INT-superpowers-4` | D | D | No | No | No | No | Pass |
| `INT-superpowers-5` | D | D | No | No | No | No | Pass |

## INT-claude-feature-dev (5 runs)

| Run | Entry after Phase 3 | Exit before Phase 4 architecture | Two orchestrators | Broad clarification repeat | Implementation tasks | Automatic architecture invocation | Result |
| --- | --- | --- | --- | --- | --- | --- |
| `INT-claude-feature-dev-1` | D | D | No | No | No | No | Pass |
| `INT-claude-feature-dev-2` | D | D | No | No | No | No | Pass |
| `INT-claude-feature-dev-3` | D | D | No | No | No | No | Pass |
| `INT-claude-feature-dev-4` | D | D | No | No | No | No | Pass |
| `INT-claude-feature-dev-5` | D | D | No | No | No | No | Pass |

`INT-claude-feature-dev-2` presents an unselected “Architecture-first
handoff” option (line 32), then expressly says “No option was selected”
(line 36) and “does not … invoke architecture design automatically” (line
60). It is therefore not an automatic-invocation violation.

## INT-spec-kit (5 runs)

| Run | Entry after `speckit.clarify` | Exit before `speckit.plan` | Two orchestrators | Broad specification repeat | Planning tasks | Automatic `speckit.plan` invocation | Result |
| --- | --- | --- | --- | --- | --- | --- |
| `INT-spec-kit-1` | D | D | No | No | No | No | Pass |
| `INT-spec-kit-2` | D | D | No | No | No | No | Pass |
| `INT-spec-kit-3` | D | D | No | No | No | No | Pass |
| `INT-spec-kit-4` | D | D | No | No | No | No | Pass |
| `INT-spec-kit-5` | D | D | No | No | No | No | Pass |

## NEG-brainstorming (5 runs)

| Run | Impact-refiner artifacts / impact refinement | Invented repository evidence | Ordinary ideation | Result |
| --- | --- | --- | --- | --- |
| `NEG-brainstorming-1` | No | No | Yes | Pass |
| `NEG-brainstorming-2` | No | No | Yes | Pass |
| `NEG-brainstorming-3` | No | No | Yes | Pass |
| `NEG-brainstorming-4` | No | No | Yes | Pass |
| `NEG-brainstorming-5` | No | No | Yes | Pass |

These are ordinary product ideation outputs. They explicitly frame the task as
early ideation with no repository assumptions (for example,
`NEG-brainstorming-1` lines 1–3) and contain no `REQ-###`, `INV-###`,
`IMP-###`, `DEC-###`, or `AC-###` impact-refiner artifacts.

## NEG-planning (5 runs)

| Run | Impact-refiner exit artifact-free | Normal planning continues | Re-refinement / impact ledger | Mere handoff or refusal | Result |
| --- | --- | --- | --- | --- | --- |
| `NEG-planning-1` | Yes | Yes | No | No | Pass |
| `NEG-planning-2` | Yes | Yes | No | No | Pass |
| `NEG-planning-3` | Yes | Yes | No | No | Pass |
| `NEG-planning-4` | Yes | Yes | No | No | Pass |
| `NEG-planning-5` | Yes | Yes | No | No | Pass |

All five perform the requested normal planning rather than activating the
impact-refiner. They contain implementation sequences/tasks, but that is
required behavior for this negative case, not a violation. No run emits
impact-ledger IDs or substitutes a handoff/refusal for the requested plan.

## Aggregate

| Metric | Result |
| --- | --- |
| Runs scored | 30 / 30 |
| Passes | 25 |
| Fails | 5 |
| Exact INT entries | 15 / 20 |
| Exact INT exits | 20 / 20 |
| Confirmed prohibited-action violations | 0 |
| Repeated broad ideation/clarification | 0 |
| Two-orchestrator activation | 0 |
| Automatic next-framework invocation | 0 |
| Implementation tasks in an INT report | 0 |
| NEG-brainstorming violations | 0 / 5 |
| NEG-planning violations | 0 / 5 |

## Recommendation

**Fail the Task 4 green corpus under strict scoring.** The corpus is safe on
the hard non-overlap prohibitions, and all Superpowers, Claude feature-dev,
Spec Kit, and negative runs pass. However, generic mode fails its exact entry
contract in every repetition: it creates a canonical impact report before the
request is concrete enough for repository inspection. The generic adapter or
entrypoint needs an explicit gate that declines/defer impact refinement until
the clarified requirement and repository scope are available, while retaining
the current user-owned planning exit.
