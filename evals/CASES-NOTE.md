# Case catalog contract note (v0.5)

`cases.json` is byte-pinned by the golden-contract tests and the sealed
batch identity, so this note lives beside it rather than inside it.

The positive cases predate the v0.4/0.5 Fast Scan contract. The default
skill path now answers a single turn with scan → `needs_input`/ask → stop,
and the canonical one-turn report those rubrics expect requires the
explicit "yes" turn a single-turn harness never sends. A one-repetition
Claude Code smoke recorded exactly that shape — negatives 5/5, positives
0/8 with 7/8 following the documented stop-for-confirmation path — see
[`results/claude-v0.5-smoke/scorecard.md`](results/claude-v0.5-smoke/scorecard.md).

Scoring positives against v0.5+ therefore requires either a second "yes"
turn per positive case (the structure the lineage cases already use) or a
Fast-Scan-aware rubric. The negative cases remain valid as-is. Revising
`cases.json` itself is a golden-contract change: update the pinned SHA-256
in `tests/test_eval_cases.py` and `tests/test_eval_harness_contract.py`
deliberately, never as a side effect.
