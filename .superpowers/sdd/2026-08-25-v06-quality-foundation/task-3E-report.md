# Task 3E Report — Make zero-path graph coverage refinable

## Root cause and hypothesis

`_validate_graph_coverage()` applied its uncovered-high-risk-node gate to every
receipt node, including inventory-only nodes that belonged to no receipt path.
The approved hypothesis was confirmed: only nodes in at least one receipt path
are path-addressable impact evidence. The fix derives `path_nodes` from receipt
paths and applies the existing gate only to that set.

## RED evidence

Before the production change, the new focused command was run:

```text
python3 -m unittest -q \
  tests.test_rir_controller.RirControllerTest.test_finalize_accepts_supplied_only_zero_path_coverage_with_unrelated_license \
  tests.test_rir_controller.RirControllerTest.test_graph_coverage_rejects_unselected_high_risk_node_on_available_path
```

It failed exactly at the uncovered-node gate:

```text
ValueError: uncovered high-risk graph node NODE-018
```

The failing receipt has a seven-character `LICENSE` high-risk (`legal/policy`)
inventory node, zero paths, a separate explicit provider frontier on
`NODE-001`, and one supplied-only unknown impact with empty `graph_path_keys`
and a nonempty rationale. This directly observes the previously uncovered
high-risk graph-node failure.

## GREEN evidence and safety control

The same focused command passed after the change. The zero-path test finalizes
the supplied-only analysis as `published`.

The retained fail-closed safety control is
`test_graph_coverage_rejects_unselected_high_risk_node_on_available_path`:
`NODE-018` (`LICENSE`) participates in `PATH-001`, while the analysis selects
no path, supplies no matching verified invariant token, and has a frontier only
on `NODE-001`. It continues to raise
`uncovered high-risk graph node NODE-018`.

## Verification

- `.quality-venv/bin/mypy scripts evals/harness` — passed (42 files)
- `.quality-venv/bin/ruff check scripts skills/requirements-impact-refiner/scripts evals/harness tests` — passed
- `.quality-venv/bin/ruff format --check scripts skills/requirements-impact-refiner/scripts evals/harness tests` — passed (115 files)
- `python3 -m unittest -q tests.test_rir_controller tests.test_semantic_validation` — passed (95 tests)
- `python3 -m unittest discover -s tests -q` — passed (722 tests, 21 skipped)
- Root and installed-skill controller mirrors are byte-identical.

## Self-review

The change is limited to the high-risk coverage domain: selected-path identity,
unknown supplied-only rationale/evidence requirements, confidence ceilings,
resolved-state protection, invariant token coverage, and frontier coverage are
unchanged. No receipt schema, renderer, graph generation, or user-facing UX was
modified.
