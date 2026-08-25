# Task 5 Report — Extract lineage and finalize orchestration

## Implementation

- Added byte-identical root/installed-skill `rir_lineage.py` modules containing
  current-lineage discovery, legacy key-map recovery, stable ID allocation,
  key mapping, graph-backed scope projection, delta calculation, history
  carry-forward, and canonical compact-state construction.
- Added byte-identical root/installed-skill `rir_finalize.py` modules containing
  the validation, graph-context selection, lineage projection, controller
  metadata write, report publication/readback, display rendering, draft
  consumption, and result construction sequence.
- Kept `rir_controller.py` as the stable public facade. It exposes the original
  request/result class identities and exact one-argument `finalize_refinement`
  signature while passing a complete runtime map into the extracted finalizer.
  The map retains facade fault-injection points, including `_consume`, graph
  context/coverage hooks, metadata publication, renderers, and result factory.
- Removed the old controller lineage/finalize implementations. Its compatibility
  names now alias the extracted lineage functions, and finalize is a thin
  wrapper over the extracted module.
- Added the public graph-delivery `verify_receipt_sources` alias required by
  promoted Fast Scan finalization, so finalize consumes only public dependency
  interfaces.

## Preserved behavior

- Revision-two projection preserves `IMP-001`, produces
  `delta.unchanged == ["IMP-001"]`, retains prior immutable history, and
  renders the same structured graph path/provenance. Its literal canonical
  state SHA-256 remains
  `581e4e0a02dbfccd81d5b8eac2e3cb323770433cd05b0467610c13f5846f9bfa`.
- The sealed facade flow retains Markdown SHA-256
  `0245b2f3a7af219a62e9887121e6459e467fa737a4502b35f3e343107569d39e`
  and the Task 1 facade fixture remains unchanged.
- Validation and mutation order remains root/bounds/draft, lock/reload,
  graph context and coverage, state build/canonicalization, controller metadata,
  report publish/readback/render, and finally draft consumption. The published
  result fields and facade `FinalizeResult` identity remain exact.
- Promoted Fast Scan and persisted trace receipt paths retain their request,
  receipt, source, digest, and coverage checks. A separate Python 3.9 direct
  extracted-finalizer run successfully promoted and published a Fast Scan.

## Dependency isolation

- Lineage resolves contracts, storage, compact state, impact report/renderer,
  and report store only as exact regular non-symlink siblings beside the module.
  Storage→report-store and report-store→compact/renderer object identities are
  validated before use.
- Finalize resolves its exact local lineage and graph-delivery siblings, then
  validates their contracts, storage, report, schema, and coordinator wiring.
  It does not plain-import another root's controller modules or reach into
  private contract/storage/graph/lineage functions.
- Clean canonical, conflicting alias, repeated load, vacated alias, and
  root-versus-installed-skill states are covered. Selective alias replacement
  is also covered: a stale but path-local renderer/report/storage or graph
  delivery is re-executed from the same safe sibling under a deterministic hash
  with coherent local dependencies. Unsafe files and invalid existing hashes
  still fail closed.
- No runtime third-party dependency or import cycle was introduced. The
  deferred Task 3 `_graph_draft_identity` helper was deliberately untouched.

## Atomic packaging

- Added only the existing `scripts/rir_lineage.py` and
  `scripts/rir_finalize.py` root paths to the byte-identical
  `payload_identity.ROOT_FILES` mirrors.
- Packaging tests require and mutate both root paths as part of functional
  payload identity. Installed-skill copies remain covered by recursive skill
  payload discovery and explicit byte-parity assertions.

## TDD evidence

- Initial RED: eight lineage/finalize tests failed only because both extracted
  modules were absent.
- Lineage GREEN: four tests passed for literal revision/digest parity, public
  allocation/mapping/legacy interfaces, current-lineage loading, and complete
  root/skill dependency isolation; facade/controller expansion then passed 91
  tests.
- Finalize GREEN: the combined initial lineage/finalize suite passed eight
  tests for the sealed Markdown digest, result identity, facade signature and
  `_consume` injection, mirror parity, and conflict/repeat/vacation wiring.
- Packaging RED→GREEN: the functional payload test failed while the new root
  paths were absent from `ROOT_FILES`, then passed after adding exactly those
  two paths.
- Full discovery exposed selective compact-state alias replacement while an
  older path-local renderer remained. A dedicated regression reproduced the
  import failure before lineage reloaded coherent hashed siblings.
- A matching finalize regression reproduced stale graph-delivery storage
  identity after selective storage replacement, then passed after safe local
  rewiring.

## Verification

- Python 3.9.6 compiled root/skill lineage, finalize, and controller modules.
  The lineage/finalize/semantic/report/controller/facade/CLI/MCP/payload suite
  passed, including the sealed facade fixture and publication failure/retry
  controls.
- Full pinned quality runner: Ruff lint/format, mypy over 48 source files, 792
  tests with 21 skips, 80.06% total branch coverage, and Bandit all passed.
  Extracted lineage reports 85.22% and finalize 56.27% branch coverage.
- Root/skill `rir_lineage.py`, `rir_finalize.py`, `rir_controller.py`,
  `rir_graph_delivery.py`, and `payload_identity.py` pairs are byte-identical.
  Functional payload hashing succeeds and `git diff --check` passes.
- The two pre-existing modified runtime pointers under
  `.requirements-impact-refiner/` were preserved and remain outside the Task 5
  staged scope.

## Self-review

The brief prohibited subagents, so review was performed directly against base
`74d01f7`. The final controller contains no shadow lineage/finalize bodies,
public facade contracts remain sealed by the Task 1 fixture, path-local module
graphs are validated through clean/conflicting/vacated/repeated states, and no
Task 3 cleanup or unrelated runtime state is included.
