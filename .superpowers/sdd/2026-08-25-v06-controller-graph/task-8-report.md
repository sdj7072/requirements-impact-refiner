# Task 8 Report — Controller/graph deterministic review gate

## Status

**Not green.** Base `8feb23d72d6762ff11ec4537e1eabd73e5bb77e3` passes every mandated
quality, real-provider, real-corpus, Python 3.9, facade, payload, mirror, and diff gate, but
the architecture review found one Important pristine-import dependency-isolation defect.
No source fixes or commits were made under the Task 8 verify-only constraint.

Review provenance: the brief requested independent architecture and security reviews, but the
controller explicitly prohibited subagents. Both review tracks were therefore performed directly.

## Findings

### Important — pristine controller import can capture a foreign `report_store` alias and fail

`scripts/rir_storage.py:55` loads `report_store` with the process-global
`importlib.import_module("report_store")`. The controller's storage validator at
`scripts/rir_controller.py:239-272` validates storage functions, limits, and `fcntl`, but does not
validate or rewire `storage.report_store` to the exact sibling. The controller then installs this
storage at `scripts/rir_controller.py:331-332` before the later lineage/finalize graph establishes
its own path-local report-store/storage identities.

A fresh Python 3.9.6 process with only a foreign `sys.modules["report_store"]` reproduced the
failure while loading `scripts/rir_controller.py`:

```text
ImportError: finalize graph delivery sibling contract is incomplete
...
ImportError: cannot load fixed finalize sibling
```

The import fails closed rather than executing the foreign callable, so this is an availability and
module-ownership defect, not demonstrated code execution. It nevertheless violates the intended
conflicting-alias isolation: a generic module name already present in the host process can prevent
the controller facade from importing at all.

The existing conflict regression at `tests/test_rir_finalize.py:175` does not cover this pristine
state. It first loads a producer controller, warming the local canonical/path-hashed dependency
graph, and only then injects foreign aliases before loading the controller under review.

Recommended correction for a later implementation task: resolve and validate the exact sibling
`report_store.py` before executing storage, inject that module while storage executes, and require
the storage/report-store identity in the controller storage contract. Add a fresh-process
regression that preloads only foreign aliases before the first controller import.

### Minor — deferred duplicate `_graph_draft_identity` remains unused in storage

`scripts/rir_storage.py:211` (and its byte-identical installed-skill mirror) still contains the
unused `_graph_draft_identity`. Runtime ownership moved to
`rir_graph_delivery.graph_draft_identity` at `scripts/rir_graph_delivery.py:880`, and repository
search found no storage-helper consumer. This has no current behavioral or security impact, but it
duplicates validation logic under the wrong module owner and can drift. This is the explicitly
deferred Task 3 helper noted by the Task 4/5 reports; remove it in a scoped cleanup after compatibility
expectations are confirmed.

No Critical findings. No other Important or Minor findings were found in the requested review
surface.

## Verification evidence

### Mandatory gates

- `.quality-venv/bin/python scripts/run-quality-gates.py` — exit 0. Ruff check and format passed
  (`138 files already formatted`), Mypy passed for 51 source files, 852 tests passed with 21 skips,
  branch coverage was 80.03% (minimum 80%), and Bandit completed because the full runner exited 0.
- `.quality-venv/bin/python scripts/run-ast-grep-canary.py` — exit 0 with exact
  `ast-grep 0.45.0`, executable SHA-256
  `a3ac7f26733e6cf56eb8f340105aa09067e87dbb1c62d63ce99d41fb5a626d6d`, one literal match,
  and adapter result of 3 nodes, 2 edges, 1 receipt.
- `.quality-venv/bin/python scripts/score-graph-corpora.py --corpora /tmp/rir-v06-corpora`
  — exit 0; all literal release gates passed.

### Python 3.9 targeted matrix

`/usr/bin/python3 --version` reported Python 3.9.6. The following focused facade/controller/storage/
graph/lineage/finalize/corpus/provider/payload/distribution matrix passed 303 tests in 46.107s:

```text
tests.test_rir_controller_facade tests.test_rir_contracts
tests.test_rir_controller tests.test_rir_controller_cli tests.test_rir_mcp_server
tests.test_rir_storage tests.test_rir_graph_delivery tests.test_compact_graph_bounds
tests.test_graph_cache tests.test_graph_coordinator tests.test_rir_lineage
tests.test_rir_finalize tests.test_graph_corpus tests.test_ast_grep_canary
tests.test_packaging tests.test_distribution
```

### Architecture, parity, payload, and diff

- Dependency direction is acyclic among the extracted modules: contracts has no controller-module
  dependency; graph delivery depends on contracts/storage; lineage depends on contracts/storage;
  finalize depends on lineage/graph delivery and their shared contracts/storage; none imports
  `rir_controller`.
- Ownership is otherwise coherent: trace and finalize public entry points delegate through bounded
  runtime maps; begin/scan and promoted Fast Scan orchestration remain in the facade as intended.
  The controller shrank from the pre-extraction 4,322-line body to 1,500 lines while retaining the
  sealed 7 dataclasses and 5 public entry points.
- The facade characterization fixture passed literal public inventory, dataclass/signature,
  canonical digest, byte-output, rejection, and filesystem assertions.
- All nine Task 1–7 changed root/installed-skill script pairs are byte-identical:
  `graph_adapter_ast_grep.py`, `graph_providers.py`, `payload_identity.py`, `rir_contracts.py`,
  `rir_storage.py`, `rir_graph_delivery.py`, `rir_lineage.py`, `rir_finalize.py`, and
  `rir_controller.py`.
- Packaging/payload mutation tests cover every new live module. `git diff --check e8599b3..HEAD`
  and current-worktree `git diff --check` both passed.

### Security review

- Lock creation/modes/contention, descriptor-relative draft/receipt traversal, durable CAS phase
  recovery, no-clobber quarantine, inode/link/mode checks, and descriptor cleanup paths passed the
  focused storage/graph tests and code audit.
- Provider executable snapshots, no-shell process spawning, process-group deadlines, stdout/stderr
  limits, UTF-8/JSON depth handling, source-bound canary reads, and complete working-state guards
  passed both focused tests and the real canary.
- Corpus destination ownership retains parent/child descriptors, cleanup is inode-directed,
  checkout/scoped-source reads are descriptor-bound, Git/provider output is bounded, and failure
  paths close descriptors. Focused lifecycle/race/overflow tests and the real external corpus run
  passed.

## Narrow corpus claim only

The passing score supports only **scoped static internal-import discovery** over two fully labelled
sources and two expected relationships within deterministic candidates from two pinned corpora:
17 non-recursive `src/click/*.py` files and 3 non-recursive root `*.js` files (20 candidates total).
Both built-in and ast-grep scored TP/FP/FN `2/0/0`, precision 1.0, recall 1.0, no undisclosed
high-risk misses, and zero provider disagreement. Built-in still disclosed unknown frontier 276.
Performance was median 1,262 ms, hard maximum 4,848 ms, and compact output 5,699 bytes. These results
do not establish repository-wide, recursive, cross-language, semantic, call/data-flow, or general
graph accuracy.

## Worktree preservation

The pre-existing modified pointer files remained the only dirty tracked paths throughout review:

```text
 M .requirements-impact-refiner/cache/graph/v1/current
 M .requirements-impact-refiner/reports/RPT-001/current.json
```

Task 8 added only this report; no source files were edited and no commit was created.

---

## Fix round 1 — isolate the pristine storage report graph

This section supersedes the non-green status for the Important finding above. The Important
pristine-import finding is fixed; the Minor unused `_graph_draft_identity` remains deliberately
deferred.

### Root cause and correction

The failure originated at storage import, where `importlib.import_module("report_store")` could
capture an arbitrary process-global alias before the controller's path-local lineage/finalize graph
was established. Storage now resolves a coherent exact-sibling graph for `compact_state.py`,
`impact_report.py`, `impact_renderer.py`, and `report_store.py` through the same
canonical/conflict/path-hash/vacated-alias state machine used by lineage. Each sibling must be a
regular non-symlink file beside storage, satisfy its used contract, and retain the required object
identities (`report_store.compact_state`, `report_store.impact_renderer`, and
`impact_renderer.compact_state`/`impact_report`). Temporary aliases are restored even on load
failure, so foreign aliases remain untouched.

The controller storage contract now independently validates the same exact sibling paths,
dependency identities, result/error types, and every report-store/renderer/state member used by
the controller graph before accepting a storage module. No storage transaction, lock, CAS,
recovery, byte, mode, error, or mutation-order function changed. Root and installed-skill storage
and controller files remain byte-identical. The deferred storage `_graph_draft_identity` was not
changed.

### TDD evidence

- RED: a fresh Python 3.9 process preloaded plausible foreign `compact_state`,
  `impact_renderer`, and `report_store` modules, then loaded root and installed-skill controllers.
  Base `8feb23d` failed at first root import with `cannot load fixed finalize sibling` caused by
  `finalize graph delivery sibling contract is incomplete`.
- RED: isolated copied storage accepted no fixed dependency boundary and failed with the global
  `No module named 'report_store'` instead of rejecting an incomplete or symlinked local compact
  state. An invalid expected path-hash module was likewise not examined.
- GREEN: both pristine controllers now import with exact path-local storage/report graphs; all
  foreign sentinel modules remain installed and no sentinel callable runs. Root and skill
  controllers each bind storage, graph delivery, lineage, and finalize to their own coherent
  report graph.
- GREEN: incomplete and symlinked local dependencies plus an invalid expected hash fail closed
  with deterministic storage-sibling errors. A measured in-process conflict/vacation regression
  verifies foreign-alias preservation and exact path-hash reuse.

### Fix-round verification

- Python 3.9.6 focused storage/lineage/finalize/graph/controller/facade/CLI/MCP/report/payload
  matrix: 195 tests passed.
- Full pinned quality runner: Ruff check/format and Mypy passed; 855 tests passed with 21 controlled
  skips; branch coverage was 80.01%; Bandit passed; final exit status was 0.
- Real pinned ast-grep 0.45.0 canary passed with the unchanged executable SHA-256
  `a3ac7f26733e6cf56eb8f340105aa09067e87dbb1c62d63ce99d41fb5a626d6d`.
- Real scoped corpus score passed: 20 deterministic candidates, 2 fully labelled sources,
  2 relationships, both providers TP/FP/FN `2/0/0`, precision/recall 1.0, zero disagreement,
  built-in frontier 276, median 1,165.5 ms, hard maximum 4,406 ms, compact output 5,701 bytes.
- Root/installed-skill `rir_storage.py` and `rir_controller.py` are byte-identical; packaging payload
  mutation coverage and `git diff --check` pass.
- The two pre-existing runtime pointer modifications remain unstaged and unchanged. No new runtime
  dependency or import cycle was introduced.
