# Compact State Contract

Author one UTF-8 JSON object using the fields below. JSON is the authored representation; scripts validate it and render both user views. Do not read `schemas/compact-state.schema.json`; it is a distribution contract for external tooling, not model guidance. Correct validation errors from this contract and the validator's exact message. Do not author an independent Markdown ledger.

## Required state

- `schema_version`: `1`.
- `report`: stable `RPT-###`, positive revision, exact predecessor Markdown SHA-256 or `none`, and `pre-decision`/`post-decision` phase.
- `settings`: resolved audience/delivery and each source.
- `original_requirement`, `refined_requirement`: one stable `REQ-###`; a concrete decision only after selection.
- `current_behavior`, `preserved_invariants`: every relevant `INV-###`, evidence level, evidence basis, affected impacts, and requirement link.
- `impacts`: every `IMP-###` with requirement, category, severity, state, evidence level/basis, invariants, decisions, and criteria.
- `decision_needed`: one question with two or three distinct options before selection; otherwise `null`.
- `decisions`: empty before selection; afterward, each `DEC-###` records choice, requirement, accepted impacts, and rationale.
- `delta`: all nine categories with every current/predecessor impact exactly once.
- `history`, `criteria`, `unresolved`, `scope`, `handoff`: the same facts required by the canonical report.
- `summary`: exactly one user-facing row per impact. Severity/status must equal the impact; explain changed feature, possible issue, affected user/feature, trigger, and prevention/check.

Never use a future `AC-###` as current evidence. `accepted` requires a decision; `resolved` requires current evidence. Only `blocked` and `deferred` impacts appear under `unresolved`, each with rationale and owner. Before selection, option mechanics stay in `decision_needed`.

## Publish

Write the candidate JSON to a temporary workspace path, then run:

```sh
python3 "$SKILL_DIR/scripts/publish-impact-report.py" \
  --repo-root REPOSITORY_ROOT STATE.json
```

Exit 0 means both append-only artifacts and the atomic current pointer were verified. Exit 1 means state, rendering, or lineage is invalid; correct the state and rerun. Exit 2 with `"fallback":"full-inline"` means persistence is unavailable; render Markdown from the candidate and return it inline:

```sh
python3 "$SKILL_DIR/scripts/render-impact-report.py" STATE.json --format markdown
```

For published `compact` delivery, render the stored revision JSON with `--format compact`. For `full`, render with `--format markdown`. Return script output without rewriting its facts. Stop at Planning Handoff; do not plan or implement.
