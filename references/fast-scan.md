# Fast Scan

Use this reference for the default one-call impact preview.

Call `rir_scan` once with `repo_root`, the user's exact change request, supplied evidence, and presentation mode. Return `display_text` verbatim. Do not rewrite paths, risks, provenance, candidates, frontier, timing, or cache status.

`complete` means the bounded inventory and graph closed within 30 seconds. `partial` means known paths are useful but unknown impact remains. `needs_input` means no trustworthy repository-backed seed was available; show at most three returned candidates and ask for one concrete boundary.

High or critical risk never triggers detailed refinement automatically. Ask whether the user wants it. If no, stop. If yes, read `controller-workflow.md` and exactly one integration adapter, then call `rir_begin` with `scan_id`. The promoted draft already owns the graph receipt: do not call `rir_trace_impact`. Finalize once with the supplied `graph_receipt_id`.

CLI fallback:

~~~sh
python3 "$SKILL_DIR/scripts/rir-controller.py" scan --repo-root REPO --input REQUEST.json
~~~

Use `--json` only when a machine client needs `scan_id`. If MCP and CLI are unavailable, disclose that `full-inline` cannot persist or promote a Fast Scan receipt.
