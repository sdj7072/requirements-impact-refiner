# Claude Code v0.5.0 behavioral smoke — scorecard

This is a **single-repetition smoke batch**, not a sealed five-repetition
release evaluation. It exists to replace the "structural probe only" rows
with actually recorded behavior. Nothing here promotes any environment to
`verified`.

## Composition

| Field | Value |
| --- | --- |
| client | Claude Code 2.1.237 (Agent-tool subagent context) |
| model | claude-fable-5 / claude-opus-5 (session-inherited per agent) |
| plugins enabled | requirements-impact-refiner 0.5.0, superpowers 6.3.0 |
| cases | 13 of 17 core cases carrying the `claude-code` mode (8 POS, 5 NEG) |
| repetitions | 1 per case |
| prompt form | the harness's canonical `request + "Repository evidence:" bullets`, verbatim, no skill hints |
| scoring | `score_smoke.py` — deterministic; reuses the harness's negative regexes and the shipped validator |

## Mechanical results

| Group | Result |
| --- | --- |
| Negatives | **5/5 pass** — no refinement IDs, no report-workflow markers |
| Positives | **0/8 pass** — no canonical report produced in the single turn |

## Reading the result honestly

**The negative half is genuine trigger evidence.** All five skip-list cases
held, including the near-boundary `NEG-planning` case whose output states
verbatim: *"requirements-impact-refiner correctly excluded — the impact
report is already approved."* The bootstrap's exclusion rule fired by name
on Claude Code. `NEG-debugging` performed pure diagnosis, `NEG-code-review`
reviewed a real PR, `NEG-brainstorming` and `NEG-generic-prd` ran their own
workflows — none leaked ledger IDs or report structure.

**The positive half measures a contract mismatch, not a simple failure.**
7 of 8 positive runs engaged the skill and executed the documented v0.5
default path exactly: Fast Scan (MCP tool absent in the subagent context,
so the documented CLI fallback) → `needs_input`, because the runs execute
inside a real repository (polaris) where the case's supplied evidence does
not exist → returned the renderer-owned question verbatim → stopped. The
canonical report the rubric expects requires the explicit "yes" turn that
a one-turn harness never sends — the same multi-turn structure the lineage
cases already model. 1 of 8 (`POS-deletion`) did not engage the skill and
answered as a coding agent (its prose nonetheless covered all three
must_detect topics).

Two contract-revision items follow for the case catalog, not the skill:
the positive cases predate the v0.4/0.5 Fast Scan flow and need either a
second "yes" turn or a Fast-Scan-aware rubric; and the harness's
supplied-evidence-only assumption conflicts with a real-repo execution
context, which the scan correctly refuses to fabricate around.

**Environmental caveats.** Subagent context differs from an interactive
session (its own system prompt; MCP tools unavailable, exercising the CLI
fallback instead). Parallel agents shared one scratchpad and overwrote each
other's scan-request files; every affected agent detected the mutation,
refused the foreign content, and re-ran from a fresh file — an unplanned
but real exercise of the input-integrity checks. One launch
(`POS-authorization`) was blocked by the host's action classifier and
succeeded on retry; the retry is the recorded run.

## Per-case verdicts

See `scores.json` (mechanical verdicts with per-case detail, including
informational must_detect keyword hits that are NOT adjudications) and
`raw/<case>/final.md` (verbatim final outputs).
