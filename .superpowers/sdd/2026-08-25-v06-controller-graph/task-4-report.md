# Task 4 Report — Extract graph binding and compact delivery

## Implementation

- Added byte-identical root/installed-skill `rir_graph_delivery.py` modules for
  compact graph selection and byte budgeting, canonical source-inventory
  digests, durable trace intent, persisted receipt validation/binding/recovery,
  receipt context loading, graph coverage validation, and `trace_impact`
  orchestration.
- Kept `rir_controller.py` as the stable public facade. Its graph entry point
  and fault-injection helpers are thin wrappers over graph delivery. A complete
  validated runtime map carries the current facade's storage operations,
  canonical byte helpers, clock/deadline boundary, cleanup/binding hooks, and
  `TraceResult` factory, preserving the existing public type identity and test
  interception points.
- Preserved the compact limits at 48 nodes, 16 paths, 16 frontier entries, and
  24,000 canonical JSON bytes. Receipt/cache/draft validation and mutation
  ordering, canonical receipt/draft bytes, SHA-256 bindings, stable validation
  errors, shared deadline, frontier disclosure, no-clobber quarantine, and
  recovery behavior remain covered by the pre-existing controller/facade
  matrix.
- Kept promoted Fast Scan context in the controller rather than introducing a
  graph-delivery dependency on Fast Scan. The unused Task 3 storage helper was
  deliberately retained as required.

## Approved zero-path behavior

- A graph-enabled impact with `graph_path_keys: []`, unknown evidence, no
  coverage rationale, and a receipt containing no paths can finalize. The
  bound context records empty path keys, `None` rationale, and unknown graph
  confidence.
- The exception does not weaken path-bearing coverage. A high-risk node on an
  available path that is neither selected, invariant-covered, nor exposed as
  a frontier still raises the exact
  `uncovered high-risk graph node <NODE-ID>` error.

## Dependency isolation

- Graph delivery never plain-imports a process-global `rir_contracts`,
  `rir_storage`, coordinator, schema, cache, builtin, or provider module from
  another root. Every dependency must resolve to the exact regular,
  non-symlink sibling beside the delivery file and satisfy the complete used
  contract.
- Clean canonical loads are reused. Conflicting aliases are left untouched
  while deterministic path-hashed siblings are loaded. Vacated aliases reuse
  an established same-root hash, and repeated root/skill loads retain distinct
  root-local graphs.
- Coordinator reuse validates every constituent module path plus the
  builtin/cache-to-schema identities. This covers the clean-load then
  canonical-alias-vacation state found by full discovery without accepting a
  cross-root coordinator graph.
- Controller loading applies the same canonical/hash state policy to
  `rir_graph_delivery.py`; explicit runtime wiring lets independently loaded
  facade contract identities safely reuse one path-local delivery module while
  preserving the current facade result class.

## Atomic packaging

- Added only the existing `scripts/rir_graph_delivery.py` root path to the
  byte-identical root/skill `payload_identity.ROOT_FILES`. The installed-skill
  copy remains covered by the existing recursive skill payload rule.
- Packaging tests require the new root path, mutate it as part of the payload
  identity check, and verify every skill script has a byte-identical root
  mirror.

## TDD evidence

- RED: the first compact parity test failed with
  `rir_graph_delivery.py must be extracted` before the production module
  existed.
- GREEN: six initial delivery tests passed for literal compact bytes,
  order-independent source digesting, both coverage controls, cross-root
  dependency isolation, and facade/mirror wiring.
- Full discovery then exposed a clean dependency alias being vacated while its
  path-hashed coordinator remained. A dedicated clean→vacated→repeat test
  reproduced the exact wiring error before the loader reused the established
  path-local coordinator graph.
- Existing contract discovery exposed a second red state: shared delivery
  reuse across distinct path-local facade contract objects. Exact sibling-path
  validation plus the explicitly wired facade `TraceResult` factory fixed it;
  all existing contract identity tests and full discovery then passed.

## Verification

- Graph delivery/compact/cache/coordinator/controller/facade/CLI/MCP/payload:
  Python 3.9.6 compiled both root/skill controller and delivery modules and
  passed 212 tests.
- Full pinned quality runner: Ruff lint and format, mypy over 46 source files,
  782 tests with 21 skips, 80.74% total branch coverage, and Bandit all passed.
  `rir_graph_delivery.py` itself reports 82.88% branch coverage.
- Root/skill `rir_controller.py`, `rir_graph_delivery.py`, and
  `payload_identity.py` pairs are byte-identical. The functional payload
  contains both delivery copies and computes successfully.
- `git diff --cached --check` and the root/skill byte comparisons pass. The two
  pre-existing modified runtime pointers under `.requirements-impact-refiner/`
  remain unstaged and unchanged by this task.

## Self-review

The brief prohibited subagents, so final review was performed directly against
base `e639427`. The staged inventory contains only Task 4 controller/delivery,
payload, and test files plus this report. No third-party runtime dependency or
import cycle was introduced, and no Task 3 storage code was removed.
