# Controller Workflow

This reference defines detailed fallback and analysis rules. The MCP recipe in `SKILL.md` is the normal path.

Read this reference only after the user accepts detailed refinement. A promoted Fast Scan already owns its graph receipt: call `rir_begin` with `scan_id`, do not call `rir_trace_impact`, and finalize once with the returned `graph_receipt_id`.

After successful `rir_finalize`, Return `display_text` verbatim and end the current turn. Do not run commands, use tools, plan, test, or modify files; execution requires a later user turn.

## Before begin

- Resolve presentation overrides from the user's request. Otherwise the controller loads `.requirements-impact-refiner.json`; report flow normalizes to disclosed `balanced` + `full`, while explicit ask flow keeps compact delivery.
- Apply exactly one integration adapter's Entry rule.
- Send supplied `Repository evidence` unchanged. It remains inspectable when the workspace is empty.

## Between begin and finalize

Use the begin result's prior state, enums, and required analysis shape. Inspect only necessary repository evidence. Preserve behavior as invariant keys; future criteria are targets, not current evidence.

Every affected behavior gets an impact row with a user-facing consequence: name the feature, describe what may break, and state the mitigation, owner, or missing evidence. Relationships use local keys; the controller allocates numeric IDs and Delta.

A required user choice is analysis, not an early chat response. Submit a complete `pre-decision` analysis with one question and two or three mutually exclusive options. Do not create a decision ID before selection. Post-decision analysis records the supplied or selected choice and its trade-off.

`accepted` requires a decision. `resolved` requires current evidence. Only `blocked` and `deferred` remain unresolved. Do not silently remove prior impact keys.

## Transitive impact receipt

When graph tracing is enabled, inspect its compact receipt before analysis and use it as the sole graph source. Select receipt paths for each impact or record a supplied-only/unknown rationale. Keep every frontier visible; do not rerun a provider, invent a connection, or emit raw receipt JSON. Read [transitive-impact-graph.md](transitive-impact-graph.md) for confidence, same-risk reuse, disagreement, cache, Deep, and display rules.

## CLI fallback

Write strict UTF-8 request and analysis JSON files, then run the same controller sequence:

```sh
python3 "$SKILL_DIR/scripts/rir-controller.py" begin --repo-root REPO --input REQUEST.json
python3 "$SKILL_DIR/scripts/rir-controller.py" trace --repo-root REPO --draft-id DRAFT_ID --input SEEDS.json
python3 "$SKILL_DIR/scripts/rir-controller.py" finalize --repo-root REPO --draft-id DRAFT_ID --graph-receipt-id RECEIPT_ID --input ANALYSIS.json
```

Use `draft_id` from begin stdout as `DRAFT_ID` and `receipt_id` from trace stdout as `RECEIPT_ID`; `SEEDS.json` contains the trace `seeds` array. Begin/trace stdout is metadata. Successful finalize stdout is renderer-owned display text. Exit 1 means correct the analysis and reuse the draft; exit 2 means invocation or I/O failed.

## Full-inline fallback

Only when MCP and CLI are both unavailable, read `compact-state-contract.md`, the routed domain/evidence/lineage references, and the matching report template. Produce and validate the complete state and canonical Markdown inline. Disclose that persistence and fast revisions are unavailable. Stop at Planning Handoff; never begin implementation.
