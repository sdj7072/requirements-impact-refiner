from __future__ import annotations

import concurrent.futures
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SKILL_SCRIPTS = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
REPOSITORY_FIXTURE = FIXTURES / "previous-report-repository"
STATE_FIXTURE = FIXTURES / "compact-state-post-decision.json"


def load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


PREVIOUS = load_module("_test_rir_previous", SCRIPTS / "rir_previous.py")
RENDERER = PREVIOUS.RENDERER
CONTEXT = PREVIOUS.REPORT_CONTEXT


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


class PreviousLookupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = (Path(self.temporary.name) / "repository").resolve()
        shutil.copytree(REPOSITORY_FIXTURE, self.root)
        self.git("init", "-q")
        self.git("config", "user.name", "RIR Test")
        self.git("config", "user.email", "rir@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.baseline_commit = self.git("rev-parse", "HEAD").stdout.strip()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", *arguments),
            cwd=self.root,
            text=True,
            capture_output=True,
            check=check,
            env={
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": os.environ.get("PATH", ""),
            },
        )

    def request(
        self,
        text: str = "rename profile",
        evidence: tuple[str, ...] = (),
        report_id: str | None = None,
    ):
        return PREVIOUS.PreviousLookupRequest(self.root, text, evidence, report_id)

    def payload_sha256(self) -> str:
        return PREVIOUS.PAYLOAD_IDENTITY.payload_sha256(ROOT)

    def publish(
        self,
        *,
        report_id: str = "RPT-001",
        request: str = "rename profile",
        revision: int = 1,
        previous_sha256: str = "none",
        with_context: bool = True,
        payload_sha256: str | None = None,
        baseline_commit: str | None = None,
        baseline_clean: bool = True,
        inventory_available: bool = True,
        inventory_complete: bool = True,
        source_inventory_sha256: str | None = "4" * 64,
        source_inventory_git_tracked_only: bool | None = None,
        required_source_digests: dict[str, str] | None = None,
        source_recheck_complete: bool | None = None,
        repository_evidence: tuple[str, ...] = (),
    ) -> tuple[Path, dict[str, object], object | None]:
        state = json.loads(STATE_FIXTURE.read_text(encoding="utf-8"))
        state["report"] = {
            "id": report_id,
            "revision": revision,
            "previous_sha256": previous_sha256,
            "phase": "post-decision",
        }
        state["original_requirement"]["request"] = request
        report_dir = self.root / ".requirements-impact-refiner" / "reports" / report_id
        report_dir.mkdir(parents=True, exist_ok=True)
        state_path = report_dir / f"revision-{revision:04d}.json"
        markdown_path = report_dir / f"revision-{revision:04d}.md"
        state_path.write_bytes(canonical_bytes(state))
        markdown = RENDERER.IMPACT_RENDERER.render_markdown(state).encode("utf-8")
        markdown_path.write_bytes(markdown)
        markdown_sha256 = hashlib.sha256(markdown).hexdigest()
        pointer = {
            "schema_version": 1,
            "report_id": report_id,
            "revision": revision,
            "state": state_path.name,
            "markdown": markdown_path.name,
            "markdown_sha256": markdown_sha256,
        }
        (report_dir / "current.json").write_bytes(canonical_bytes(pointer))
        context = None
        if with_context:
            if required_source_digests is None:
                app = self.root / "app.py"
                required_source_digests = {"app.py": hashlib.sha256(app.read_bytes()).hexdigest()}
            context = CONTEXT.ReportContext(
                schema_version=2,
                report_id=report_id,
                revision=revision,
                markdown_sha256=markdown_sha256,
                state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest(),
                repo_root_sha256=CONTEXT.repo_root_sha256(self.root),
                requirement_sha256=CONTEXT.canonical_requirement_sha256(request),
                repository_evidence_sha256=CONTEXT.canonical_repository_evidence_sha256(
                    repository_evidence
                ),
                source_inventory_sha256=source_inventory_sha256,
                payload_sha256=payload_sha256 or self.payload_sha256(),
                created_at="2026-08-25T12:34:56Z",
                baseline_commit=self.baseline_commit
                if baseline_commit is None
                else baseline_commit,
                baseline_clean=baseline_clean,
                source_inventory_available=inventory_available,
                source_inventory_complete=inventory_complete,
                source_inventory_git_tracked_only=(
                    inventory_available and inventory_complete and baseline_clean
                    if source_inventory_git_tracked_only is None
                    else source_inventory_git_tracked_only
                ),
                required_source_digests=required_source_digests,
                source_recheck_complete=(
                    inventory_available and inventory_complete
                    if source_recheck_complete is None
                    else source_recheck_complete
                ),
            )
            CONTEXT.publish_report_context(self.root, context)
        return report_dir, pointer, context

    def test_exact_clean_match_is_fresh(self):
        _report_dir, _pointer, context = self.publish()

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(
            dict(context.required_source_digests),
            {"app.py": hashlib.sha256((self.root / "app.py").read_bytes()).hexdigest()},
        )
        self.assertTrue(context.source_recheck_complete)
        self.assertEqual(result.status, "fresh")
        self.assertEqual(result.changed_paths, ())
        self.assertEqual(result.changed_count, 0)
        self.assertEqual((result.report_id, result.revision), ("RPT-001", 1))
        self.assertEqual(result.baseline_commit, self.baseline_commit)
        self.assertIn("**Freshness:** fresh", result.display_text or "")

    def test_fresh_lookup_preserves_detailed_request_and_evidence_bounds(self):
        request_text = "x" * 5000
        evidence = ("e" * 5000, "duplicate", "duplicate")
        self.publish(request=request_text, repository_evidence=evidence)

        result = PREVIOUS.lookup_previous(self.request(request_text, evidence))

        self.assertEqual(result.status, "fresh")
        self.assertIsNotNone(result.display_text)
        self.assertEqual(result.candidates, ())

    def test_requirement_normalization_selects_the_same_lineage(self):
        self.publish(request="프로필 Caf\u00e9 이름 변경")

        result = PREVIOUS.lookup_previous(self.request("  프로필  Cafe\u0301 이름\n변경  "))

        self.assertEqual(result.status, "fresh")

    def test_other_requirement_never_returns_previous_body(self):
        self.publish()

        result = PREVIOUS.lookup_previous(self.request("delete account"))

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)
        self.assertIsNone(result.report_id)
        self.assertIsNone(result.markdown_sha256)

    def test_changed_or_reordered_repository_evidence_discloses_no_body(self):
        evidence = ("first", "second", "first")
        self.publish(repository_evidence=evidence)
        exact = self.request(evidence=evidence)
        changed = self.request(evidence=("changed",))
        reordered = self.request(evidence=("second", "first", "first"))
        deduplicated = self.request(evidence=("first", "second"))

        self.assertEqual(PREVIOUS.lookup_previous(exact).status, "fresh")
        self.assertEqual(PREVIOUS.lookup_previous(changed).status, "none")
        self.assertIsNone(PREVIOUS.lookup_previous(changed).display_text)
        self.assertEqual(PREVIOUS.lookup_previous(reordered).status, "none")
        self.assertEqual(PREVIOUS.lookup_previous(deduplicated).status, "none")

    def test_valid_shaped_compact_only_state_tamper_discloses_no_body(self):
        report_dir, pointer, _context = self.publish()
        state_path = report_dir / str(pointer["state"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["settings"]["audience"] = "simple"
        state_path.write_bytes(canonical_bytes(state))

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_valid_shaped_graph_paths_tamper_discloses_no_body(self):
        report_dir, pointer, _context = self.publish()
        state_path = report_dir / str(pointer["state"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["graph_paths"] = [
            {
                "impact": "IMP-001",
                "paths": [
                    {
                        "id": "PATH-001",
                        "labels": ["tampered", "consumer"],
                        "providers": ["tampered-provider"],
                        "confidence": "verified-provider",
                        "locations": ["tampered.py:1"],
                    }
                ],
            }
        ]
        state_path.write_bytes(canonical_bytes(state))

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_repository_without_report_storage_returns_none(self):
        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_unsafe_or_unbounded_report_inventory_fails_closed(self):
        reports = self.root / ".requirements-impact-refiner" / "reports"
        reports.mkdir(parents=True)
        (reports / "RPT-001").write_text("not a directory\n", encoding="utf-8")
        result = PREVIOUS.lookup_previous(self.request())
        self.assertEqual(result.status, "none")

        (reports / "RPT-001").unlink()
        (reports / "RPT-001").mkdir()
        with mock.patch.object(PREVIOUS, "MAX_REPORT_ENTRIES", 0):
            result = PREVIOUS.lookup_previous(self.request())
        self.assertEqual(result.status, "none")

    def test_current_pointer_schema_and_revision_paths_fail_closed(self):
        report_dir, pointer, _context = self.publish()
        pointer_path = report_dir / "current.json"
        variants = [
            b"not-json\n",
            canonical_bytes({**pointer, "schema_version": True}),
            canonical_bytes({**pointer, "report_id": "RPT-002"}),
            canonical_bytes({**pointer, "revision": 0}),
            canonical_bytes({**pointer, "markdown_sha256": "bad"}),
            canonical_bytes({**pointer, "state": "../escape.json"}),
        ]
        for payload in variants:
            with self.subTest(payload=payload[:80]):
                pointer_path.write_bytes(payload)
                result = PREVIOUS.lookup_previous(self.request())
                self.assertEqual(result.status, "none")
                self.assertIsNone(result.display_text)

    def test_missing_symlinked_or_tampered_revision_artifacts_fail_closed(self):
        report_dir, pointer, _context = self.publish()
        state_path = report_dir / str(pointer["state"])
        markdown_path = report_dir / str(pointer["markdown"])
        state_bytes = state_path.read_bytes()
        markdown_bytes = markdown_path.read_bytes()

        markdown_path.unlink()
        self.assertEqual(PREVIOUS.lookup_previous(self.request()).status, "none")
        markdown_path.write_bytes(markdown_bytes + b"tamper")
        self.assertEqual(PREVIOUS.lookup_previous(self.request()).status, "none")
        markdown_path.write_bytes(markdown_bytes)

        state_path.unlink()
        state_path.symlink_to(self.root / "app.py")
        self.assertEqual(PREVIOUS.lookup_previous(self.request()).status, "none")
        state_path.unlink()
        state_path.write_bytes(state_bytes)
        self.assertEqual(PREVIOUS.lookup_previous(self.request()).status, "fresh")

    def test_payload_identity_failure_discloses_no_report_body(self):
        self.publish()
        with mock.patch.object(
            PREVIOUS.PAYLOAD_IDENTITY,
            "payload_sha256",
            side_effect=ValueError("injected unsafe payload"),
        ):
            result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_other_repository_root_never_returns_previous_body(self):
        self.publish()
        other = (Path(self.temporary.name) / "other").resolve()
        shutil.copytree(self.root, other, ignore=shutil.ignore_patterns(".git"))

        result = PREVIOUS.lookup_previous(
            PREVIOUS.PreviousLookupRequest(other, "rename profile", ())
        )

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_payload_mismatch_is_not_a_reusable_report(self):
        self.publish(payload_sha256="f" * 64)

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)
        self.assertEqual(
            result.reason,
            "previous report schema or payload identity is incompatible with this runtime",
        )

    def test_incomplete_source_inventory_is_stale_never_fresh(self):
        self.publish(inventory_complete=False)

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("source inventory", result.reason)
        self.assertIsNotNone(result.display_text)

    def test_relevant_ignored_inventory_source_is_stale(self):
        gitignore = self.root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8") + "ignored.py\n", encoding="utf-8"
        )
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore relevant source")
        self.baseline_commit = self.git("rev-parse", "HEAD").stdout.strip()
        (self.root / "ignored.py").write_text("relevant = True\n", encoding="utf-8")
        self.publish(source_inventory_git_tracked_only=False)

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("Git-tracked", result.reason)

    def test_unavailable_source_inventory_is_stale_never_fresh(self):
        self.publish(
            inventory_available=False,
            inventory_complete=False,
            source_inventory_sha256=None,
        )

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")

    def test_pre_recheck_v2_context_migrates_to_stale(self):
        report_dir, pointer, _context = self.publish()
        context_path = report_dir / f"revision-{pointer['revision']:04d}.context-v2.json"
        payload = json.loads(context_path.read_text(encoding="utf-8"))
        del payload["required_source_digests"]
        del payload["source_recheck_complete"]
        context_path.write_bytes(canonical_bytes(payload))

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("recheck", result.reason.lower())
        self.assertIsNotNone(result.display_text)

    def test_unclean_recorded_baseline_is_stale_never_fresh(self):
        self.publish(baseline_clean=False, baseline_commit=None)

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("baseline", result.reason)

    def test_dirty_tracked_file_is_stale_with_deterministic_changed_path(self):
        self.publish()
        (self.root / "app.py").write_text("changed = True\n", encoding="utf-8")

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertEqual(result.changed_paths, ("app.py",))
        self.assertEqual(result.changed_count, 1)

    def test_untracked_file_is_stale_with_deterministic_changed_path(self):
        self.publish()
        (self.root / "zeta.py").write_text("z = 1\n", encoding="utf-8")
        (self.root / "alpha.py").write_text("a = 1\n", encoding="utf-8")

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertEqual(result.changed_paths, ("alpha.py", "zeta.py"))
        self.assertEqual(result.changed_count, 2)

    def test_ignored_explicit_source_bytes_are_rechecked(self):
        gitignore = self.root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8") + "ignored.py\n", encoding="utf-8"
        )
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore explicit source")
        self.baseline_commit = self.git("rev-parse", "HEAD").stdout.strip()
        ignored = self.root / "ignored.py"
        ignored.write_text("value = 'report'\n", encoding="utf-8")
        recorded = hashlib.sha256(ignored.read_bytes()).hexdigest()
        self.publish(
            required_source_digests={"ignored.py": recorded},
            source_recheck_complete=True,
            source_inventory_git_tracked_only=True,
        )
        ignored.write_text("value = 'changed'\n", encoding="utf-8")

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(self.git("status", "--porcelain").stdout, "")
        self.assertEqual(result.status, "stale")
        self.assertIn("source", result.reason.lower())

    def test_source_mutation_between_git_samples_is_caught_by_final_byte_sample(self):
        gitignore = self.root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8") + "ignored.py\n", encoding="utf-8"
        )
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore explicit source")
        self.baseline_commit = self.git("rev-parse", "HEAD").stdout.strip()
        ignored = self.root / "ignored.py"
        ignored.write_text("value = 'report'\n", encoding="utf-8")
        self.publish(
            required_source_digests={
                "ignored.py": hashlib.sha256(ignored.read_bytes()).hexdigest()
            },
            source_recheck_complete=True,
            source_inventory_git_tracked_only=True,
        )
        real_hash = PREVIOUS._hash_required_sources
        samples = 0

        def hash_sources(root, required, deadline):
            nonlocal samples
            observed = real_hash(root, required, deadline)
            samples += 1
            if samples == 1:
                ignored.write_text("value = 'changed between samples'\n", encoding="utf-8")
            return observed

        with mock.patch.object(PREVIOUS, "_hash_required_sources", side_effect=hash_sources):
            result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(samples, 2)
        self.assertEqual(self.git("status", "--porcelain").stdout, "")
        self.assertEqual(result.status, "stale")
        self.assertIn("source", result.reason.lower())

    def test_ignored_attributes_and_filter_aba_around_status_cannot_hide_source_bytes(self):
        info_exclude = self.root / ".git" / "info" / "exclude"
        info_exclude.write_text(
            info_exclude.read_text(encoding="utf-8") + "\n.gitattributes\n",
            encoding="utf-8",
        )
        self.publish()
        app = self.root / "app.py"
        app.write_text(
            "def rename_profile(name: str) -> str:\n    return 'compromised'\n",
            encoding="utf-8",
        )
        attributes = self.root / ".gitattributes"
        real_runner = PREVIOUS._run_git_command

        def runner(root, arguments, deadline, **kwargs):
            if "status" not in arguments:
                return real_runner(root, arguments, deadline, **kwargs)
            attributes.write_text("app.py filter=race\n", encoding="utf-8")
            self.git(
                "config",
                "filter.race.clean",
                "sed s/return.*compromised.*/return\\ name.strip()/",
            )
            try:
                result = real_runner(root, arguments, deadline, **kwargs)
                self.assertIsNotNone(result)
                return PREVIOUS._GitCommandResult(result.returncode, b"")
            finally:
                self.git("config", "--unset-all", "filter.race.clean")
                attributes.unlink()

        with mock.patch.object(PREVIOUS, "_run_git_command", side_effect=runner):
            result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("source", result.reason.lower())
        self.assertFalse(attributes.exists())

    def test_source_recheck_byte_bound_overflow_is_stale(self):
        self.publish()

        with mock.patch.object(PREVIOUS, "MAX_SOURCE_RECHECK_BYTES", 1):
            result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("byte limit", result.reason.lower())

    def test_required_source_symlink_is_stale_even_when_target_bytes_match(self):
        gitignore = self.root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8") + "ignored-*.py\n", encoding="utf-8"
        )
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore explicit source links")
        self.baseline_commit = self.git("rev-parse", "HEAD").stdout.strip()
        source = self.root / "ignored-source.py"
        target = self.root / "ignored-target.py"
        source.write_text("value = 'same'\n", encoding="utf-8")
        target.write_bytes(source.read_bytes())
        self.publish(
            required_source_digests={
                "ignored-source.py": hashlib.sha256(source.read_bytes()).hexdigest()
            },
            source_recheck_complete=True,
            source_inventory_git_tracked_only=True,
        )
        source.unlink()
        source.symlink_to(target.name)

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(self.git("status", "--porcelain").stdout, "")
        self.assertEqual(result.status, "stale")
        self.assertIn("source", result.reason.lower())

    def test_assume_unchanged_and_skip_worktree_flags_are_stale(self):
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.publish()
                self.git("update-index", flag, "app.py")

                result = PREVIOUS.lookup_previous(self.request())

                self.assertEqual(result.status, "stale")
                self.assertIn("index", result.reason)
                inverse = (
                    "--no-assume-unchanged"
                    if flag == "--assume-unchanged"
                    else "--no-skip-worktree"
                )
                self.git("update-index", inverse, "app.py")

    def test_local_core_worktree_redirect_is_stale(self):
        self.publish()
        redirected = Path(self.temporary.name) / "redirected"
        redirected.mkdir()
        self.git("config", "core.worktree", str(redirected))

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("worktree", result.reason.lower())

    def test_descriptor_safe_git_control_parsing_and_packed_head(self):
        git_dir = self.root / ".git"
        self.git("pack-refs", "--all", "--prune")
        self.assertEqual(PREVIOUS._filesystem_head(git_dir), self.baseline_commit)
        head_path = git_dir / "HEAD"
        original_head = head_path.read_bytes()
        try:
            for payload in (
                b"\xff\n",
                b"not-a-head\n",
                b"ref: ../escape\n",
                b"ref: refs/heads/missing\n",
            ):
                with self.subTest(head=payload):
                    head_path.write_bytes(payload)
                    with self.assertRaises(PREVIOUS._GitUnavailable):
                        PREVIOUS._filesystem_head(git_dir)
        finally:
            head_path.write_bytes(original_head)

        config = git_dir / "config"
        original_config = config.read_bytes()
        try:
            config.write_bytes(original_config + b"\n[include]\npath = /tmp/foreign\n")
            self.assertFalse(PREVIOUS._configured_worktree_matches(self.root, git_dir))
            config.write_bytes(original_config + b"\n[broken\n")
            with self.assertRaises(PREVIOUS._GitUnavailable):
                PREVIOUS._configured_worktree_matches(self.root, git_dir)
        finally:
            config.write_bytes(original_config)

        oversized = self.root / "oversized-control"
        oversized.write_bytes(b"x" * 5)
        with self.assertRaises(PREVIOUS._GitUnavailable):
            PREVIOUS._read_git_control_file(oversized, 4)

        unsafe_root = Path(self.temporary.name) / "unsafe-git-marker"
        unsafe_root.mkdir()
        marker = unsafe_root / ".git"
        marker.write_text("gitdir: missing\n", encoding="utf-8")
        with self.assertRaises(PREVIOUS._GitUnavailable):
            PREVIOUS._filesystem_git_dir(unsafe_root)
        marker.unlink()
        marker.symlink_to(git_dir, target_is_directory=True)
        with self.assertRaises(PREVIOUS._GitUnavailable):
            PREVIOUS._filesystem_git_dir(unsafe_root)

    def test_head_change_between_freshness_probes_is_stale(self):
        self.publish()
        real_head = PREVIOUS._filesystem_head
        head_calls = 0

        def head(git_dir):
            nonlocal head_calls
            head_calls += 1
            if head_calls > 1:
                return "f" * 40
            return real_head(git_dir)

        with mock.patch.object(PREVIOUS, "_filesystem_head", side_effect=head):
            result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("HEAD", result.reason)

    def test_replacement_ref_is_never_fresh_at_the_same_head(self):
        self.publish()
        original_head = self.git("rev-parse", "HEAD").stdout.strip()
        (self.root / "replacement.py").write_text("replacement = True\n", encoding="utf-8")
        self.git("add", "replacement.py")
        self.git("commit", "-qm", "replacement commit")
        replacement = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("checkout", "-q", original_head)
        (self.root / "replacement.py").unlink(missing_ok=True)
        self.git("replace", original_head, replacement)

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(self.git("rev-parse", "HEAD").stdout.strip(), original_head)
        self.assertEqual(result.status, "stale")
        self.assertIn("replace", result.reason.lower())
        self.git("replace", "-d", original_head)
        self.assertEqual(PREVIOUS.lookup_previous(self.request()).status, "fresh")

    def test_index_flag_race_hiding_a_real_edit_is_stale(self):
        self.publish()
        real_runner = PREVIOUS._run_git_command
        raced = False

        def runner(root, arguments, deadline, **kwargs):
            nonlocal raced
            result = real_runner(root, arguments, deadline, **kwargs)
            if not raced and "ls-files" in arguments:
                raced = True
                self.git("update-index", "--assume-unchanged", "app.py")
                (self.root / "app.py").write_text("hidden = True\n", encoding="utf-8")
            return result

        with mock.patch.object(PREVIOUS, "_run_git_command", side_effect=runner):
            result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("index", result.reason.lower())

    def test_changed_head_is_stale_and_lists_commit_delta_paths(self):
        self.publish()
        (self.root / "new_api.py").write_text("enabled = True\n", encoding="utf-8")
        self.git("add", "new_api.py")
        self.git("commit", "-qm", "change source")

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertEqual(result.changed_paths, ("new_api.py",))
        self.assertEqual(result.changed_count, 1)
        self.assertIn("HEAD", result.reason)

    def test_missing_git_is_stale_and_changed_count_is_unavailable(self):
        self.publish()
        empty_path = Path(self.temporary.name) / "empty-bin"
        empty_path.mkdir()

        with mock.patch.dict(PREVIOUS.os.environ, {"PATH": str(empty_path)}):
            result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertEqual(result.changed_paths, ())
        self.assertIsNone(result.changed_count)
        self.assertIsNotNone(result.display_text)

    def test_git_timeout_is_stale_and_process_group_is_bounded(self):
        self.publish()
        binary_dir = Path(self.temporary.name) / "slow-bin"
        binary_dir.mkdir()
        git = binary_dir / "git"
        git.write_text("#!/bin/sh\n/bin/sleep 5\n", encoding="utf-8")
        git.chmod(0o755)

        started = time.monotonic()
        with mock.patch.dict(PREVIOUS.os.environ, {"PATH": str(binary_dir)}):
            result = PREVIOUS.lookup_previous(self.request())
        elapsed = time.monotonic() - started

        self.assertEqual(result.status, "stale")
        self.assertLess(elapsed, 1.0)
        self.assertLessEqual(result.elapsed_ms, 999)

    def test_context_read_that_exhausts_operation_deadline_discloses_no_body(self):
        self.publish()
        real_load = PREVIOUS.REPORT_CONTEXT.load_report_context
        real_check = PREVIOUS._check_deadline
        exhausted = False

        def load_context(*args, **kwargs):
            nonlocal exhausted
            value = real_load(*args, **kwargs)
            exhausted = True
            return value

        def check_deadline(deadline):
            if exhausted:
                raise PREVIOUS._LookupDeadline("injected deadline exhaustion")
            return real_check(deadline)

        with (
            mock.patch.object(
                PREVIOUS.REPORT_CONTEXT, "load_report_context", side_effect=load_context
            ),
            mock.patch.object(PREVIOUS, "_check_deadline", side_effect=check_deadline),
        ):
            result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_checkout_transform_config_is_stale_at_the_same_commit(self):
        self.publish()
        for key, value in (
            ("core.autocrlf", "false"),
            ("core.eol", "lf"),
            ("core.attributesfile", ".git/custom-attributes"),
            ("filter.demo.required", "false"),
        ):
            with self.subTest(key=key):
                self.git("config", key, value)
                self.git("checkout", "-q", "--", "app.py")

                result = PREVIOUS.lookup_previous(self.request())

                self.assertEqual(result.status, "stale")
                self.assertIn("transform", result.reason.lower())
                self.git("config", "--unset-all", key)

        global_home = Path(self.temporary.name) / "global-home"
        global_home.mkdir()
        (global_home / ".gitconfig").write_text(
            '[filter "global"]\n\trequired = false\n', encoding="utf-8"
        )
        with mock.patch.dict(PREVIOUS.os.environ, {"HOME": str(global_home)}):
            result = PREVIOUS.lookup_previous(self.request())
        self.assertEqual(result.status, "stale")
        self.assertIn("transform", result.reason.lower())

        self.git("config", "extensions.worktreeConfig", "true")
        self.git("config", "--worktree", "core.eol", "lf")
        result = PREVIOUS.lookup_previous(self.request())
        self.assertEqual(result.status, "stale")
        self.assertIn("transform", result.reason.lower())

    def test_info_or_tracked_attributes_are_stale(self):
        nested = self.root / "nested"
        nested.mkdir()
        (nested / ".gitattributes").write_text("*.py text\n", encoding="utf-8")
        self.git("add", "nested/.gitattributes")
        self.git("commit", "-qm", "add nested attributes")
        self.baseline_commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.publish()

        tracked = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(tracked.status, "stale")
        self.assertIn("attributes", tracked.reason.lower())

        (nested / ".gitattributes").unlink()
        self.git("add", "nested/.gitattributes")
        self.git("commit", "-qm", "remove nested attributes")
        self.baseline_commit = self.git("rev-parse", "HEAD").stdout.strip()
        report_dir = self.root / ".requirements-impact-refiner" / "reports" / "RPT-001"
        shutil.rmtree(report_dir)
        self.publish()
        info_attributes = self.root / ".git" / "info" / "attributes"
        info_attributes.write_text("*.py text\n", encoding="utf-8")
        self.git("checkout", "-q", "--", "app.py")

        info = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(info.status, "stale")
        self.assertIn("attributes", info.reason.lower())

    def test_transform_config_race_during_lookup_is_stale(self):
        self.publish()
        real_runner = PREVIOUS._run_git_command
        sampled = False

        def runner(root, arguments, deadline, **kwargs):
            nonlocal sampled
            result = real_runner(root, arguments, deadline, **kwargs)
            if not sampled and "config" in arguments and "--get-regexp" in arguments:
                sampled = True
                self.git("config", "filter.race.clean", "cat")
            return result

        with mock.patch.object(PREVIOUS, "_run_git_command", side_effect=runner):
            result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("transform", result.reason.lower())

    def test_any_gitlink_is_stale_even_when_submodule_is_clean(self):
        child = (Path(self.temporary.name) / "child").resolve()
        child.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=child, check=True)
        subprocess.run(
            ["git", "config", "user.email", "rir@example.invalid"], cwd=child, check=True
        )
        subprocess.run(["git", "config", "user.name", "RIR Test"], cwd=child, check=True)
        (child / "child.py").write_text("value = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "child.py"], cwd=child, check=True)
        subprocess.run(["git", "commit", "-qm", "child"], cwd=child, check=True)
        self.git(
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(child),
            "deps/child",
        )
        self.git("commit", "-qam", "add submodule")
        self.baseline_commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.publish()

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "stale")
        self.assertIn("gitlink", result.reason.lower())

    def test_legacy_single_lineage_never_discloses_identity_or_body(self):
        self.publish(with_context=False)

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "none")
        self.assertEqual((result.report_id, result.revision), (None, None))
        self.assertIsNone(result.display_text)
        self.assertIsNone(result.created_at)
        self.assertIsNone(result.source_inventory_sha256)

    def test_legacy_state_for_another_requirement_returns_none(self):
        self.publish(request="delete account", with_context=False)

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_legacy_match_is_not_disclosed_when_repository_has_another_lineage(self):
        self.publish(with_context=False)
        self.publish(report_id="RPT-002", request="another request")

        result = PREVIOUS.lookup_previous(self.request())

        self.assertIn(result.status, {"none", "ambiguous"})
        self.assertIsNone(result.display_text)

    def test_multiple_matching_lineages_are_ambiguous_without_body(self):
        self.publish(report_id="RPT-001")
        self.publish(report_id="RPT-002")

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.display_text)
        self.assertIsNone(result.report_id)
        self.assertIsNone(result.revision)
        self.assertEqual(
            tuple(
                (candidate.report_id, candidate.revision, candidate.created_at)
                for candidate in result.candidates
            ),
            (
                ("RPT-001", 1, "2026-08-25T12:34:56Z"),
                ("RPT-002", 1, "2026-08-25T12:34:56Z"),
            ),
        )

        selected = PREVIOUS.lookup_previous(self.request(report_id="RPT-002"))

        self.assertEqual(selected.status, "fresh")
        self.assertEqual((selected.report_id, selected.revision), ("RPT-002", 1))
        self.assertEqual(selected.candidates, ())

    def test_report_id_must_belong_to_exact_private_candidate_set(self):
        self.publish(report_id="RPT-001")
        self.publish(report_id="RPT-002", repository_evidence=("other",))

        foreign = PREVIOUS.lookup_previous(self.request(report_id="RPT-999"))
        wrong_evidence = PREVIOUS.lookup_previous(self.request(report_id="RPT-002"))

        for result in (foreign, wrong_evidence):
            self.assertEqual(result.status, "none")
            self.assertIsNone(result.display_text)
            self.assertIsNone(result.report_id)
            self.assertEqual(result.candidates, ())

    def test_ambiguous_candidate_disclosure_is_sorted_and_bounded_to_sixteen(self):
        for number in range(1, 18):
            self.publish(report_id=f"RPT-{number:03d}")

        with mock.patch.object(PREVIOUS, "OPERATION_TIMEOUT_SECONDS", 2.0):
            result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(len(result.candidates), 16)
        self.assertEqual(
            tuple(candidate.report_id for candidate in result.candidates),
            tuple(f"RPT-{number:03d}" for number in range(1, 17)),
        )
        self.assertTrue(
            all(
                set(vars(candidate)) == {"report_id", "revision", "created_at"}
                for candidate in result.candidates
            )
        )

    def test_unsafe_pointer_fails_closed_without_body(self):
        report_dir, _pointer, _context = self.publish()
        (report_dir / "current.json").write_bytes(b'{"schema_version":1}\n')

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_pointer_fifo_cannot_hang_or_disclose_body(self):
        report_dir, _pointer, _context = self.publish()
        pointer_path = report_dir / "current.json"
        pointer_path.unlink()
        os.mkfifo(pointer_path)

        started = time.monotonic()
        result = PREVIOUS.lookup_previous(self.request())

        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_state_fifo_cannot_hang_or_disclose_body(self):
        report_dir, pointer, _context = self.publish()
        state_path = report_dir / str(pointer["state"])
        state_path.unlink()
        os.mkfifo(state_path)

        started = time.monotonic()
        result = PREVIOUS.lookup_previous(self.request())

        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_context_fifo_cannot_hang_or_fall_back_to_legacy(self):
        report_dir, pointer, _context = self.publish()
        context_path = report_dir / f"revision-{pointer['revision']:04d}.context-v2.json"
        context_path.unlink()
        os.mkfifo(context_path, mode=0o600)

        started = time.monotonic()
        result = PREVIOUS.lookup_previous(self.request())

        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_tampered_state_cannot_be_rendered_under_valid_markdown_identity(self):
        report_dir, pointer, _context = self.publish()
        state_path = report_dir / str(pointer["state"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["summary"][0]["possible_issue"] = "tampered body"
        state_path.write_bytes(canonical_bytes(state))

        result = PREVIOUS.lookup_previous(self.request())

        self.assertEqual(result.status, "none")
        self.assertIsNone(result.display_text)

    def test_renderer_returns_only_structured_header_and_existing_compact_summary(self):
        _report_dir, _pointer, _context = self.publish()

        result = PREVIOUS.lookup_previous(self.request())
        text = result.display_text or ""

        self.assertTrue(text.startswith("## Previous Impact Report\n\n"))
        for field in (
            "**Freshness:** fresh",
            "**Report:** `RPT-001` revision 1",
            "**Created:** 2026-08-25T12:34:56Z",
            f"**Commit:** `{self.baseline_commit}`",
            "**Changed files:** 0",
            "## Change Impact Summary",
        ):
            self.assertIn(field, text)
        for full_report_block in (
            "# Requirements Impact Report",
            "## Original Requirement",
            "## Current Behavior",
            "## Impact Ledger",
        ):
            self.assertNotIn(full_report_block, text)

    def test_renderer_returns_empty_text_for_none_and_ambiguous(self):
        self.publish()
        state = json.loads(STATE_FIXTURE.read_text(encoding="utf-8"))
        result = PREVIOUS.lookup_previous(self.request("another request"))
        self.assertEqual(result.status, "none")

        self.assertEqual(RENDERER.render_previous(result, state), "")
        ambiguous = replace(
            result,
            status="ambiguous",
            reason="multiple lineages",
            candidates=(
                PREVIOUS.PreviousReportCandidate("RPT-001", 1, "2026-08-25T12:34:56Z"),
                PREVIOUS.PreviousReportCandidate("RPT-002", 1, "2026-08-25T12:34:56Z"),
            ),
        )
        self.assertEqual(RENDERER.render_previous(ambiguous, state), "")

    def test_concurrent_pointer_refresh_never_mixes_revision_fields_and_body(self):
        report_dir, pointer_one, context_one = self.publish()
        self.assertIsNotNone(context_one)
        _, pointer_two, _context_two = self.publish(
            revision=2,
            previous_sha256=str(pointer_one["markdown_sha256"]),
        )
        pointer_path = report_dir / "current.json"
        first_bytes = canonical_bytes(pointer_one)
        second_bytes = canonical_bytes(pointer_two)
        stop = threading.Event()

        def refresh() -> None:
            index = 0
            while not stop.is_set():
                temporary = report_dir / f".current-test-{threading.get_ident()}-{index}"
                temporary.write_bytes(first_bytes if index % 2 == 0 else second_bytes)
                os.replace(temporary, pointer_path)
                index += 1

        clean_git = PREVIOUS._GitSnapshot(
            available=True,
            commit=self.baseline_commit,
            changed_paths=(),
            changed_count=0,
            worktree_clean=True,
            reason="pinned clean Git evidence",
        )
        with mock.patch.object(PREVIOUS, "_probe_git", return_value=clean_git):
            writer = threading.Thread(target=refresh)
            writer.start()
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    results = tuple(
                        executor.map(
                            lambda _index: PREVIOUS.lookup_previous(self.request()), range(40)
                        )
                    )
            finally:
                stop.set()
                writer.join(timeout=2)

        self.assertFalse(writer.is_alive())
        self.assertTrue(results)
        for result in results:
            self.assertEqual(result.status, "fresh")
            self.assertIn(result.revision, {1, 2})
            self.assertIn(
                f"**Report:** `RPT-001` revision {result.revision}", result.display_text or ""
            )
            expected = pointer_one if result.revision == 1 else pointer_two
            self.assertEqual(result.markdown_sha256, expected["markdown_sha256"])

    def test_thousand_ignored_generated_files_keep_warm_p95_within_budget(self):
        self.publish()
        for number in range(2, 26):
            report_dir, _pointer, _context = self.publish(
                report_id=f"RPT-{number:03d}", request=f"unrelated requirement {number}"
            )
            for artifact in range(4):
                (report_dir / f"unrelated-{artifact}.artifact").write_text(
                    "bounded irrelevant artifact\n", encoding="utf-8"
                )
        generated = self.root / "generated"
        generated.mkdir()
        for index in range(1000):
            (generated / f"generated-{index:04d}.txt").write_text("ignored\n", encoding="utf-8")
        samples = []
        self.assertEqual(PREVIOUS.lookup_previous(self.request()).status, "fresh")
        for _index in range(20):
            started = time.perf_counter_ns()
            result = PREVIOUS.lookup_previous(self.request())
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
            self.assertEqual(result.status, "fresh")
        samples.sort()
        p95 = samples[math.ceil(len(samples) * 0.95) - 1]

        self.assertLessEqual(p95, 300.0, samples)

    def test_maximum_source_recheck_budget_keeps_warm_p95_within_budget(self):
        sources = self.root / "bounded-sources"
        sources.mkdir()
        file_bytes = PREVIOUS.MAX_SOURCE_RECHECK_BYTES // PREVIOUS.MAX_REQUIRED_SOURCE_DIGESTS
        required = {}
        for index in range(PREVIOUS.MAX_REQUIRED_SOURCE_DIGESTS):
            source = sources / f"source-{index:02d}.py"
            source.write_bytes(bytes([index]) * file_bytes)
            relative = source.relative_to(self.root).as_posix()
            required[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
        self.git("add", "bounded-sources")
        self.git("commit", "-qm", "bounded source recheck fixture")
        self.baseline_commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.publish(
            required_source_digests=required,
            source_recheck_complete=True,
            source_inventory_git_tracked_only=True,
        )

        samples = []
        self.assertEqual(PREVIOUS.lookup_previous(self.request()).status, "fresh")
        for _index in range(20):
            started = time.perf_counter_ns()
            result = PREVIOUS.lookup_previous(self.request())
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
            self.assertEqual(result.status, "fresh")
        samples.sort()
        p95 = samples[math.ceil(len(samples) * 0.95) - 1]

        self.assertLessEqual(p95, 300.0, samples)


class PreviousDependencyAndPackagingTest(unittest.TestCase):
    def sample_result(self, **changes):
        values = {
            "status": "fresh",
            "report_id": "RPT-001",
            "revision": 1,
            "markdown_sha256": "1" * 64,
            "created_at": "2026-08-25T12:34:56Z",
            "baseline_commit": "2" * 40,
            "changed_paths": (),
            "changed_count": 0,
            "requirement_sha256": "3" * 64,
            "source_inventory_sha256": "4" * 64,
            "display_text": None,
            "reason": "identity is fresh",
            "elapsed_ms": 1,
        }
        values.update(changes)
        return PREVIOUS.PreviousReportResult(**values)

    def test_request_and_result_contracts_reject_malformed_public_values(self):
        with self.assertRaises(TypeError):
            PREVIOUS.PreviousLookupRequest(str(ROOT), "request", ())
        for evidence in ([], ("",), (1,)):
            with self.subTest(evidence=evidence):
                with self.assertRaises(ValueError):
                    PREVIOUS.PreviousLookupRequest(ROOT, "request", evidence)
        with self.assertRaises(ValueError):
            PREVIOUS.PreviousLookupRequest(ROOT, "request", (), "foreign")

        invalid = (
            {"status": "unknown"},
            {"requirement_sha256": "bad"},
            {"changed_paths": ["a.py"]},
            {"changed_paths": ("b.py", "a.py")},
            {"changed_paths": ("a.py",), "changed_count": 0},
            {"elapsed_ms": -1},
            {"reason": ""},
            {"report_id": "bad"},
            {"revision": 0},
            {"markdown_sha256": "bad"},
            {"baseline_commit": "bad"},
            {"source_inventory_sha256": "bad"},
            {"display_text": ""},
        )
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    self.sample_result(**changes)

        with self.assertRaises(ValueError):
            self.sample_result(
                status="none",
                changed_count=None,
                changed_paths=(),
            )

    def test_changed_path_parsers_fail_closed_on_malformed_or_unbounded_git_output(self):
        for payload in (
            b"",
            b"x" * (PREVIOUS.MAX_CHANGED_PATH_BYTES + 1),
            b"\xff",
            b"../x",
            b"a\nx",
        ):
            with self.subTest(payload=payload[:20]):
                with self.assertRaises(PREVIOUS._GitUnavailable):
                    PREVIOUS._safe_changed_path(payload)

        for payload in (b"?? path", b"bad\0", b"ZZ path\0", b"R  path\0"):
            with self.subTest(status=payload):
                with self.assertRaises(PREVIOUS._GitUnavailable):
                    PREVIOUS._status_paths(payload)
        with self.assertRaises(PREVIOUS._GitUnavailable):
            PREVIOUS._diff_paths(b"path")
        with mock.patch.object(PREVIOUS, "MAX_CHANGED_PATHS", 0):
            with self.assertRaises(PREVIOUS._GitUnavailable):
                PREVIOUS._diff_paths(b"path\0")

        with self.assertRaises(PREVIOUS._GitUnavailable):
            PREVIOUS._successful(None, "Git test")
        with self.assertRaises(PREVIOUS._GitUnavailable):
            PREVIOUS._successful(PREVIOUS._GitCommandResult(1, b""), "Git test")
        with self.assertRaises(PREVIOUS._GitUnavailable):
            PREVIOUS._successful(PREVIOUS._GitCommandResult(0, b"bad\0"), "Git test")

    def test_renderer_rejects_invalid_status_state_and_revision_binding(self):
        state = json.loads(STATE_FIXTURE.read_text(encoding="utf-8"))
        malformed = types.SimpleNamespace(status="invalid")
        with self.assertRaises(ValueError):
            RENDERER.render_previous(malformed, state)

        result = self.sample_result(markdown_sha256="5" * 64)
        with self.assertRaises(ValueError):
            RENDERER.render_previous(result, {})
        with self.assertRaises(ValueError):
            RENDERER.render_previous(replace(result, revision=2), state)
        missing_identity = types.SimpleNamespace(
            status="stale",
            report_id=None,
            revision=None,
            created_at=None,
            baseline_commit=None,
            changed_count=None,
            reason="legacy",
        )
        state_without_report = dict(state)
        state_without_report["report"] = []
        with self.assertRaises(ValueError):
            RENDERER.render_previous(missing_identity, state_without_report)

    def test_root_and_skill_previous_modules_are_byte_identical(self):
        for name in ("rir_previous.py", "rir_previous_renderer.py"):
            self.assertEqual((SCRIPTS / name).read_bytes(), (SKILL_SCRIPTS / name).read_bytes())

    def test_payload_identity_includes_both_previous_runtime_modules(self):
        relative = {
            path.relative_to(ROOT).as_posix()
            for path in PREVIOUS.PAYLOAD_IDENTITY.functional_paths(ROOT)
        }
        self.assertTrue({"scripts/rir_previous.py", "scripts/rir_previous_renderer.py"} <= relative)

    def test_previous_resolves_only_path_local_dependencies_under_foreign_aliases(self):
        exact = {
            "compact_state",
            "impact_report",
            "impact_renderer",
            "payload_identity",
            "rir_report_context",
            "rir_previous_renderer",
        }
        prefixes = ("_rir_previous_", "_rir_previous_renderer_")
        preserved = {
            name: value
            for name, value in sys.modules.items()
            if name in exact or name.startswith(prefixes)
        }
        loaded = []

        def clear() -> None:
            for name in tuple(sys.modules):
                if name in exact or name.startswith(prefixes):
                    sys.modules.pop(name, None)

        def assert_local(module, directory: Path) -> None:
            self.assertEqual(
                Path(module.REPORT_CONTEXT.__file__).resolve(),
                (directory / "rir_report_context.py").resolve(),
            )
            self.assertEqual(
                Path(module.PAYLOAD_IDENTITY.__file__).resolve(),
                (directory / "payload_identity.py").resolve(),
            )
            self.assertEqual(
                Path(module.RENDERER.__file__).resolve(),
                (directory / "rir_previous_renderer.py").resolve(),
            )
            self.assertEqual(
                Path(module.RENDERER.COMPACT_STATE.__file__).resolve(),
                (directory / "compact_state.py").resolve(),
            )
            self.assertEqual(
                Path(module.RENDERER.IMPACT_RENDERER.__file__).resolve(),
                (directory / "impact_renderer.py").resolve(),
            )

        try:
            clear()
            with tempfile.TemporaryDirectory() as temporary:
                foreign_path = Path(temporary) / "foreign.py"
                foreign_path.write_text("foreign = True\n", encoding="utf-8")
                conflicts = {}
                for name in exact:
                    conflict = types.ModuleType(name)
                    conflict.__file__ = str(foreign_path)
                    sys.modules[name] = conflict
                    conflicts[name] = conflict

                root = load_module("previous_collision_root", SCRIPTS / "rir_previous.py")
                skill = load_module("previous_collision_skill", SKILL_SCRIPTS / "rir_previous.py")
                loaded.extend(("previous_collision_root", "previous_collision_skill"))
                assert_local(root, SCRIPTS)
                assert_local(skill, SKILL_SCRIPTS)
                self.assertIsNot(root.REPORT_CONTEXT, skill.REPORT_CONTEXT)
                self.assertIsNot(root.RENDERER, skill.RENDERER)
                for name, conflict in conflicts.items():
                    self.assertIs(sys.modules[name], conflict)
        finally:
            clear()
            sys.modules.update(preserved)
            for name in loaded:
                sys.modules.pop(name, None)

    def test_controller_facade_exposes_the_exact_previous_contract(self):
        controller = load_module("_test_previous_controller", SCRIPTS / "rir_controller.py")
        try:
            self.assertIs(
                controller.PreviousLookupRequest, controller.PREVIOUS.PreviousLookupRequest
            )
            self.assertIs(controller.PreviousReportResult, controller.PREVIOUS.PreviousReportResult)
            self.assertTrue(callable(controller.lookup_previous))
        finally:
            sys.modules.pop("_test_previous_controller", None)


if __name__ == "__main__":
    unittest.main()
