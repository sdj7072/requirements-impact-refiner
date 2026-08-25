# v0.6 Release and Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align every v0.6.0 artifact, prove local and remote tag installs, publish an immutable GitHub Release, and prepare marketplace submission without overstating acceptance.

**Architecture:** A version-audit script is the source of release consistency. A local annotated tag is canaried before push; the pushed tag is never replaced; a remote tag canary precedes GitHub Release creation.

**Tech Stack:** Git; GitHub CLI; Codex plugin marketplace; Claude Code plugin marketplace; Python release-audit scripts.

**Spec:** `docs/superpowers/specs/2026-08-25-v0.6-production-readiness-design.md`

## Global Constraints

- Complete all previous v0.6 plans and the sealed live-client matrix first.
- A public tag is immutable and is never force-updated or recreated.
- Version and digest mismatch blocks publication.
- Installation instructions use the immutable release tag; `main` is development-only.
- Marketplace submission and marketplace acceptance are reported as separate states.
- No release claim exceeds the sealed evidence report.

---

### Task 1: Create one version-audit contract

**Files:**
- Create: `scripts/audit-release-version.py`
- Create: `tests/test_release_version_audit.py`
- Modify: `scripts/payload_identity.py`

**Interfaces:**
- Produces: `audit_version(root: Path, expected: str) -> tuple[str, ...]`
- Consumes: manifests, skill metadata, marketplace entries, READMEs, packaging tests, release evidence metadata

- [ ] **Step 1: Write failing mismatch tests**

```python
def test_audit_finds_every_v05_surface(self):
    findings = audit_version(ROOT, "0.6.0")
    self.assertIn(".codex-plugin/plugin.json: expected 0.6.0, found 0.5.0", findings)
    self.assertIn(".claude-plugin/plugin.json: expected 0.6.0, found 0.5.0", findings)
    self.assertIn("README.md: expected release 0.6.0", findings)
```

- [ ] **Step 2: Run and observe the missing audit module**

Run: `python3 -m unittest -q tests.test_release_version_audit`

- [ ] **Step 3: Implement strict version extraction**

Parse JSON with `json`, skill frontmatter with the existing bounded metadata parser, and documentation with exact release tokens. Report every mismatch in sorted path order. `--expected 0.6.0` exits 1 on any finding and prints none on success.

- [ ] **Step 4: Verify and commit**

Run: `python3 scripts/audit-release-version.py --expected 0.5.0`

```bash
git add scripts/audit-release-version.py tests/test_release_version_audit.py scripts/payload_identity.py
git commit -m "build: add strict release version audit"
```

### Task 2: Align version 0.6.0 and current documentation

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `.agents/plugins/marketplace.json`
- Modify: `skills/requirements-impact-refiner/SKILL.md`
- Modify: `skills/using-requirements-impact-refiner/SKILL.md`
- Modify: `README.md`, `README.ko.md`, `README.ja.md`
- Modify: packaging/documentation/release tests

**Interfaces:**
- Consumes: exact `0.6.0` version and sealed v0.6 evidence report
- Produces: version-aligned plugin payload and honest compatibility tables

- [ ] **Step 1: Change expected tests before manifests**

Update packaging and documentation tests to require `0.6.0`, the Python AST statement, JS/TS structure statement, current provider evidence, current client score, and tag-based install commands.

- [ ] **Step 2: Run and capture all v0.5 mismatch failures**

Run: `python3 -m unittest -q tests.test_distribution tests.test_packaging tests.test_documentation tests.test_release_compatibility_evidence tests.test_release_version_audit`

- [ ] **Step 3: Update every release surface atomically**

Set all plugin and skill versions to `0.6.0`. Replace release installation examples with `--ref requirements-impact-refiner--v0.6.0`; label `--ref main` as development. Remove obsolete claims that built-in scanning performs no AST parsing. Update all three compatibility tables from the sealed v0.6 report only.

- [ ] **Step 4: Run the version and documentation gates**

Run: `python3 scripts/audit-release-version.py --expected 0.6.0`

Run: `python3 -m unittest -q tests.test_distribution tests.test_packaging tests.test_documentation tests.test_release_compatibility_evidence`

- [ ] **Step 5: Commit**

```bash
git add .codex-plugin .claude-plugin .agents skills README.md README.ko.md README.ja.md tests
git commit -m "release: align v0.6.0 payload and documentation"
```

### Task 3: Generate and review release notes and payload inventory

**Files:**
- Create: `docs/releases/v0.6.0.md`
- Create: `evals/results/v0.6-release/installed-payload.json`
- Create: `tests/test_v06_release_artifacts.py`

**Interfaces:**
- Consumes: Git history from v0.5.0, sealed evidence, `payload_identity.functional_paths`
- Produces: reviewed release notes and sorted payload digest inventory

- [ ] **Step 1: Write artifact integrity tests**

```python
def test_inventory_matches_functional_payload(self):
    inventory = json.loads(INVENTORY.read_text())
    observed = [row["path"] for row in inventory["files"]]
    expected = [path.relative_to(ROOT).as_posix() for path in functional_paths(ROOT)]
    self.assertEqual(observed, expected)
```

- [ ] **Step 2: Run and confirm artifacts are absent**

Run: `python3 -m unittest -q tests.test_v06_release_artifacts`

- [ ] **Step 3: Generate literal inventory and release notes**

The inventory contains path, size, and SHA-256 in sorted order plus one inventory digest. Release notes contain user-visible changes, upgrade steps, verified client matrix, graph/provider scope, performance evidence, known frontiers, and exact blocked or unverified integrations.

- [ ] **Step 4: Verify and commit**

Run: `python3 -m unittest -q tests.test_v06_release_artifacts tests.test_release_compatibility_evidence`

```bash
git add docs/releases/v0.6.0.md evals/results/v0.6-release/installed-payload.json tests/test_v06_release_artifacts.py
git commit -m "docs: prepare v0.6.0 release artifacts"
```

### Task 4: Final candidate review and main integration

**Files:**
- Verify only: entire release candidate

**Interfaces:**
- Consumes: all prior plans and artifacts
- Produces: exact candidate commit approved for local tagging

- [ ] **Step 1: Run every deterministic gate from a clean worktree**

Run: `.quality-venv/bin/python scripts/run-quality-gates.py`

Run: `.quality-venv/bin/python scripts/run-ast-grep-canary.py`

Run: `.quality-venv/bin/python scripts/score-graph-corpora.py --corpora /tmp/rir-v06-corpora`

Run: `python3 scripts/audit-release-version.py --expected 0.6.0`

Run: `python3 -m unittest discover -s tests -q`

- [ ] **Step 2: Verify sealed live evidence**

Run manifest, secret, controller, score, adjudication, and payload-digest validators against `evals/results/v0.6-release`.

- [ ] **Step 3: Request final architecture, security, evidence, UX, and release reviews**

Any Critical or Important finding returns to the owning plan. Do not tag while a finding is open.

- [ ] **Step 4: Merge the green branch to main**

Use fast-forward merge when possible. Run all gates again on merged `main`, push, and require remote CI success on the exact commit.

### Task 5: Create and verify the local immutable candidate tag

**Files:**
- No repository file changes

**Interfaces:**
- Consumes: green main commit and release notes
- Produces: local annotated tag `requirements-impact-refiner--v0.6.0`

- [ ] **Step 1: Create the local annotated tag**

Run: `candidate_sha="$(git rev-parse main)" && git tag -a requirements-impact-refiner--v0.6.0 -m "Requirements Impact Refiner v0.6.0" "$candidate_sha"`

Record `candidate_sha` in the canary evidence and require it to equal the
release inventory commit; never substitute another commit.

- [ ] **Step 2: Install Codex and Claude from the local tag**

Clone the tag into a temporary directory, register its local marketplace, install the plugin in fresh client-specific environments, and record installed versions and payload digests. Do not reuse the development plugin cache.

- [ ] **Step 3: Compare canary digests**

Require the installed functional-path inventory and aggregate digest to equal `installed-payload.json`. Run one positive two-turn and one negative case in each client.

- [ ] **Step 4: Delete the local tag on failure only**

Because the tag has not been pushed, a failed local canary removes the local tag and returns to implementation. Preserve the failed canary evidence; never reuse it as a pass.

### Task 6: Push tag, run remote canary, and publish GitHub Release

**Files:**
- Modify after verified external actions: README compatibility status only if evidence changes

**Interfaces:**
- Consumes: passing local tag canaries
- Produces: public immutable tag and GitHub Release

- [ ] **Step 1: Push the tag once**

Run: `git push origin refs/tags/requirements-impact-refiner--v0.6.0`

Never force-push or replace the tag.

- [ ] **Step 2: Install from the remote tag**

In fresh Codex and Claude environments, install `sdj7072/requirements-impact-refiner` at `requirements-impact-refiner--v0.6.0`, verify payload digest, and run the four-case tag canary.

- [ ] **Step 3: Create the GitHub Release**

Run: `gh release create requirements-impact-refiner--v0.6.0 --repo sdj7072/requirements-impact-refiner --title "Requirements Impact Refiner v0.6.0" --notes-file docs/releases/v0.6.0.md --verify-tag`

Execute only after the remote tag canary passes.

- [ ] **Step 4: Read back the release**

Run: `gh release view requirements-impact-refiner--v0.6.0 --repo sdj7072/requirements-impact-refiner --json tagName,name,isDraft,isPrerelease,url`

Require the expected tag, non-draft state, and published URL.

### Task 7: Improve repository metadata and marketplace submission state

**Files:**
- Create: `docs/releases/marketplace-submission-v0.6.0.md`
- Modify: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `.agents/plugins/marketplace.json`

**Interfaces:**
- Consumes: published release URL, tag-install evidence, logo, privacy/terms links
- Produces: complete submission packet and exact external status

- [ ] **Step 1: Write metadata validation tests**

```python
def test_marketplace_metadata_has_public_release_fields(self):
    manifest = json.loads(Path(".codex-plugin/plugin.json").read_text())
    self.assertEqual(manifest["version"], "0.6.0")
    self.assertTrue(manifest["description"])
    self.assertTrue(manifest["keywords"])
    self.assertTrue(manifest["interface"]["privacyPolicyURL"].startswith("https://"))
```

- [ ] **Step 2: Run and fix metadata gaps**

Run: `python3 -m unittest -q tests.test_distribution tests.test_packaging`

- [ ] **Step 3: Update GitHub description and topics**

Run: `gh repo edit sdj7072/requirements-impact-refiner --description "Repository-backed requirements impact and regression-risk refinement for coding agents" --add-topic agent-skills --add-topic requirements --add-topic impact-analysis --add-topic codex --add-topic claude-code`

- [ ] **Step 4: Prepare and submit available marketplace forms**

The packet includes release URL, install instructions, capability and privacy declarations, screenshots, three-locale documentation, canary evidence, support scope, and known limitations. Record each destination as `submitted`, `accepted`, `rejected`, or `blocked`; do not claim official listing from repository metadata alone.

- [ ] **Step 5: Commit submission documentation**

```bash
git add docs/releases/marketplace-submission-v0.6.0.md .codex-plugin/plugin.json .claude-plugin/marketplace.json .agents/plugins/marketplace.json tests
git commit -m "docs: record v0.6 marketplace submission"
```

### Task 8: Post-release verification and cleanup

**Files:**
- Verify only: release repository, branches, worktrees, tags, actions

**Interfaces:**
- Consumes: public release and marketplace submission packet
- Produces: clean main, no stale release branch/worktree, final release report

- [ ] **Step 1: Verify remote main, tag, release, and CI**

Read back exact SHAs with `git ls-remote`, inspect GitHub Actions conclusions, and compare release metadata.

- [ ] **Step 2: Re-run tag installation smoke**

Install without development checkout state and confirm version, tool inventory, locale output, and one complete report.

- [ ] **Step 3: Remove only merged release worktrees and branches**

Use safe branch deletion after ancestor verification. Preserve all failed or blocked evidence and never delete quarantine without explicit approval.

- [ ] **Step 4: Publish the final status**

Report exact release URL, commit, tag, CI run, client canary results, evidence manifest digest, marketplace submission states, remaining blocked integrations, and recovery instructions.
