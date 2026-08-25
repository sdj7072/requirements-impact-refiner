# Claude Code ask-flow batch — sealed at repetition 1

Planned as five repetitions of 13 claude-code cases (fixture-anchored
positives from `evals/claude-v05-cases.json`, sealed one-turn negatives)
against plugin 0.5.0's ask flow. **Stopped deliberately after repetition 1:**
mid-batch the product contract changed — the default flow moved from
scan-summary-plus-question to report-first delivery — so further
repetitions would have accumulated evidence for a retired contract.
Per `evals/CASES-NOTE.md`, a contract change retires its case protocol;
a fresh batch against the report flow supersedes this one.

## Composition

| Field | Value |
| --- | --- |
| client | Claude Code 2.1.237 (Agent-tool subagent context) |
| plugin | requirements-impact-refiner 0.5.0 (installed cache), superpowers 6.3.0 enabled |
| cases | 8 fixture-anchored positives (two-turn) + 5 sealed negatives (one-turn) |
| repetitions | 1 of 5 planned (stopped: contract change) |
| infrastructure | one session-limit interruption killed 3 negative runs and pruned the positives' fixtures mid-flight; the 3 negatives were rerun cleanly, and engaged positives continued under the skill's empty-workspace rule |

## Mechanical results (repetition 1)

| Group | Result |
| --- | --- |
| Negatives | 4/5 — `NEG-planning` referenced an existing approved report's `RPT-002` id while correctly refusing to re-run refinement; recorded as a mechanical fail, arguably a rubric artifact |
| Positives | 1/8 — `POS-payments` produced a validator-clean canonical report inline after the yes turn |

## The four findings that matter

1. **Engagement is the bottleneck, and it inverts with anchorability.**
   With fixtures present and imperative phrasing, only 3/8 positives
   engaged the skill; the other 5 acted directly on the repository —
   exactly the must_not_do violation the skill exists to prevent, and the
   opposite of the v0.5 smoke where unanchorable evidence produced 7/8
   engagement. An agent that *can* act tends to act; the bootstrap loses
   precisely when the stakes are real.
2. **The two-turn path works end-to-end when engaged.** All 3 engaged
   runs completed detailed refinement after the yes turn and produced
   full reports with sound content (tenant-key isolation, double-charge
   taxonomy, dead-letter starvation) — evidence the machinery holds.
3. **Inline-copy summarization.** 2 of 3 engaged runs wrote a
   validator-clean report to disk but abbreviated the inline copy
   (dropping Delta rows or handoff columns), violating the
   complete-inline rule; only `POS-payments` returned the canonical
   bytes inline. The rule needs mechanical teeth, not prose.
4. **Integrity behavior under chaos was excellent.** Parallel agents
   whose scratchpad inputs were overwritten by siblings detected the
   mutation, refused foreign content, and re-ran from fresh files;
   fixture deletion mid-run was disclosed and handled under the
   empty-workspace rule rather than papered over.

Findings 1 and 3 are the empirical basis for the report-first flow
change (`flow: report` default): removing the ask checkpoint removes
both the engagement cliff's most common surface and the inline
summarization opportunity.

## Artifacts

`raw/<case>/rep1/turn1.md` (and `turn2.md` for engaged positives),
`scores-rep1.json` (mechanical verdicts). `NEG-generic-prd/rep1/turn1.md`
is preserved from the completion notification because the session
restart pruned its transcript; the note inside says so.
