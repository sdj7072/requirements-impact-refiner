# Fast Scan (ask flow)

Use this reference only when the resolved `flow` is `ask`. In the default report flow the scan is internal and its display text is never the user-facing answer.

Call `rir_scan` once with `repo_root`, the user's exact change request, supplied evidence, and presentation mode. Return `display_text` verbatim. Do not rewrite paths, risks, provenance, candidates, frontier, timing, or cache status.

`complete` means the bounded inventory closed and the built-in graph finished its coverage within 30 seconds; unavailable optional external providers stay disclosed in the frontier and do not block promotion. `partial` means known paths are useful but unknown impact remains. `needs_input` means no trustworthy repository-backed seed was available; show at most three returned candidates and ask for one concrete boundary.

High or critical risk never triggers detailed refinement automatically. `display_text` already ends with the refinement question, so return it verbatim and stop. If the user's next answer is no, stop. If yes, read `controller-workflow.md` and exactly one integration adapter, then call `rir_begin` with `scan_id`. The promoted draft already owns the graph receipt: do not call `rir_trace_impact`. Finalize once with the supplied `graph_receipt_id`.

CLI fallback:

~~~sh
python3 "$SKILL_DIR/scripts/rir-controller.py" scan --repo-root REPO --input REQUEST.json
~~~

Use `--json` only when a machine client needs `scan_id`. If MCP and CLI are unavailable, disclose that `full-inline` cannot persist or promote a Fast Scan receipt.
