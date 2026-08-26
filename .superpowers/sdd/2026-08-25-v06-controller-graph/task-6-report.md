# Task 6 Report — Pinned ast-grep provider canary

## Implementation

- Added the exact `ast-grep-cli==0.45.0` provider-only requirement and a
  repository fixture/config/rule with literal scan, adapter-node, adapter-edge,
  range, evidence, and source-SHA expectations.
- Added `scripts/run-ast-grep-canary.py`. Its public scan command is exactly:

  ```text
  ast-grep scan --json=stream --config evals/ast-grep-canary/sgconfig.yml evals/ast-grep-canary/fixture
  ```

- The runner resolves one executable, records its platform-specific SHA-256 at
  runtime, requires the exact `ast-grep 0.45.0` version, and compares that same
  executable digest across version, scan, direct pattern, and adapter execution.
- Provider execution uses the existing snapshotting/bounded subprocess runner,
  plus a 10-second canary deadline, 512 KiB stdout limit, 64 KiB JSONL row
  limit, 128-row limit, and depth-64 JSON bound. Malformed, non-object,
  traversing, schema-drifted, source-unbound, oversized, or deep output fails
  closed.
- `--rewrite`, `--update`, `--update-all`, `--interactive`, `-r`, `-U`, and
  `-i` are rejected. The constructed scan command is fixed and contains no
  update or rewrite option.
- The canary compares the literal scan match set, invokes
  `graph_adapter_ast_grep` over the same fixture, compares literal
  `ProviderResult` nodes/edges/source hashes, and verifies the adapter raw
  receipt digest against a direct observation from the same resolved binary.
- The official 0.45.0 literal-pattern stream omits `metaVariables` when it has
  no bindings. The root and installed-skill adapters now accept exactly the
  official seven-field shape or the existing eight-field shape with a mapping
  `metaVariables`; all other schema drift remains rejected.
- The official macOS universal binary is 100,333,008 bytes. The root and
  installed-skill provider executable snapshot ceiling was raised from 64 MiB
  to a still-bounded 128 MiB so the exact official platform binary can be
  snapshotted instead of substituted or sliced.
- Added an independent Python 3.13 `provider-canary` CI job. It installs only
  `requirements-provider-canary.txt` and runs the canary. Existing test and
  quality jobs, global `contents: read`, runtime manifests,
  `requirements-quality.txt`, and no-auto-install runtime behavior are
  unchanged.
- Classified the canary as a root-only CI/quality utility; it is not copied
  into the installed skill payload.

## TDD evidence

- The print-contract test first failed because the canary runner was absent,
  then passed after the minimal `--print-command` implementation.
- Read-only flag, malformed/deep/oversized JSONL, and bounded fake-provider
  tests first failed on missing safety interfaces, then passed after their
  bounded implementations.
- Real 0.45.0 integration first failed at the previous 64 MiB executable bound,
  then exposed the official missing-`metaVariables` shape. A focused adapter
  regression reproduced that second failure before the schema correction.
- The provider-job documentation test first failed because `provider-canary`
  was absent, then passed after the independent job was added.
- The quality-venv sibling-discovery test first failed because the isolated
  provider environment did not inherit venv PATH, then passed after resolution
  preferred the active interpreter's bin directory.

## Verification

- Exact provider install/version: requirement already satisfied at 0.45.0;
  `.quality-venv/bin/ast-grep --version` printed `ast-grep 0.45.0`.
- Print contract: exact command above.
- Focused canary/adapter/provider/CI/docs/packaging suite: 121 tests passed,
  3 controlled skips.
- Pinned quality runner: Ruff lint and format passed; mypy passed over 49 source
  files; 808 tests passed with 21 controlled skips; branch coverage was 80.06%;
  security gate passed.
- Fresh Apple Python 3.9.6 discovery, with bytecode cache redirected to `/tmp`
  because the host cache is sandbox-protected: 808 tests passed with 24
  controlled skips.
- Real local canary result:

  ```json
  {"adapter":{"edges":2,"nodes":3,"receipts":1},"executable_sha256":"a3ac7f26733e6cf56eb8f340105aa09067e87dbb1c62d63ce99d41fb5a626d6d","matches":1,"status":"ok","version":"ast-grep 0.45.0"}
  ```

- `git status --porcelain=v1` was byte-identical before and after the real
  canary. Root/installed adapter and provider copies compare byte-identical;
  `git diff --check` passed.

## Scope preservation

The pre-existing changes to
`.requirements-impact-refiner/cache/graph/v1/current` and
`.requirements-impact-refiner/reports/RPT-001/current.json` were preserved and
remain outside the Task 6 staged scope. No subagents were used, as required by
the brief.

## Fix round 1 — complete read-only and source identity boundaries

### Review findings addressed

- Replaced the five-file manifest check with a bounded, byte-exact working-state
  guard around the complete canary. It runs exactly `git status
  --porcelain=v1 -z --untracked-files=all` before and after, with optional Git
  locks disabled, a five-second deadline, 2 MiB stdout and 64 KiB stderr bounds,
  a minimal environment, and temporary state directed to the system temporary
  directory outside the repository. Missing Git, non-repositories, nonzero
  status, stderr, timeout, or oversized output fail closed.
- The porcelain bytes include every tracked modification and every non-ignored
  untracked path, so changed, deleted, renamed, and newly created paths anywhere
  in the repository change the snapshot. Each reported existing path is also
  bound to bounded mode/link/size/mtime and content identity, so edits to a path
  that was already dirty or already untracked cannot hide behind unchanged
  porcelain text. Pre-existing dirty paths are preserved because only
  before/after equality is required.
- Git-ignored paths are intentionally outside this exact contract: the required
  command does not pass `--ignored`, and a regression records that behavior.
  The real provider commands remain a fixed read-only allowlist, executable
  snapshots use the provider runner's private system-temporary directory, and
  the Git subprocess also uses the system temporary directory, so expected
  canary/provider temporary outputs do not target the repository.
- Replaced the source `lstat`/`resolve`/`read_bytes` sequence with
  descriptor-anchored traversal. The runner opens the exact fixture root, every
  parent, and the source using `O_NOFOLLOW`; holds the full descriptor chain
  through the read; requires a single-link bounded regular file; and compares
  device, inode, mode, link count, size, and nanosecond mtime across pathname,
  opened descriptor, post-read descriptor, every parent, and the root.
- Source reads are bounded to 128 KiB and all platform `OSError` details are
  normalized. Regressions cover the valid control, symlink parent/file, hard
  link, file replacement, file symlink swap, parent symlink swap, mode change,
  and injected read error.
- Replaced heuristic canary flag scanning with exact accepted command shapes:
  version, the printable full scan command, its executable-free scan arguments,
  and the fixed direct-pattern shape with a bounded pattern and safe relative
  path. Every other shape, including separated/attached long mutation flags,
  attached rewrites, mutating clusters, and `--` variants, fails closed.
- Strengthened both canonical provider runners with option-aware parsing.
  `-rreplacement`, `-r=value`, standalone `-r`, `-U`/`-i`, and supported
  clusters containing them are rejected. Known long/short value options consume
  their values, preventing false rejection of safe values such as a pattern
  named `update`; arguments after `--` are treated as literal paths.

### Fix-round TDD and verification

- Complete-state tests first failed because the runner exposed neither an exact
  Git snapshot nor a guard. Fake provider actions now prove detection of
  unrelated tracked changes, deletion, rename, and new untracked output, while
  changes to already-dirty and already-untracked contents are also detected;
  unchanged pre-existing graph/report pointers do not false-fail. Separate fake
  subprocesses prove output-bound and timeout rejection.
- Descriptor tests first failed on hard links and missing controlled race/read
  hooks. They now pass for every valid, symlink, replacement, parent-swap,
  mode-identity, and deterministic read-error case above.
- Argument tables first demonstrated acceptance of attached rewrites and
  mutating clusters plus false rejection of safe option values. Canary and
  provider valid/invalid tables now pass, including explicit `--` semantics.
- Focused fake/real canary, provider, adapter, CI/documentation, and packaging
  suite: 127 tests passed. The real 0.45.0 output remained byte-for-byte the
  same JSON result recorded above.
- Pinned quality runner: Ruff lint/format passed; mypy passed over 49 source
  files; 822 tests passed with 21 controlled skips; branch coverage was 80.07%;
  security checks passed.
- Fresh Apple Python 3.9.6 compile/discovery: 822 tests passed with 24 controlled
  skips.
- External `git status --porcelain=v1 -z --untracked-files=all` snapshots were
  380 bytes before and after the real canary and compared byte-identical.
  Root/installed provider copies also compared byte-identical, and
  `git diff --check` passed.
