import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "providers"


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PROVIDERS = load_module("_rir_graph_providers", "graph_providers.py")
AST_GREP = load_module("graph_adapter_ast_grep", "graph_adapter_ast_grep.py")
CODEGRAPH = load_module("graph_adapter_codegraph", "graph_adapter_codegraph.py")
SCIP = load_module("graph_adapter_scip", "graph_adapter_scip.py")
JOERN = load_module("graph_adapter_joern", "graph_adapter_joern.py")


class FakeClock:
    def __init__(self):
        self.current = 0.0

    def monotonic(self):
        return self.current


class Completed:
    def __init__(self, stdout=b"", *, returncode=0, stdout_truncated=False):
        self.stdout = stdout
        self.stderr = b""
        self.returncode = returncode
        self.timed_out = False
        self.stdout_truncated = stdout_truncated
        self.stderr_truncated = False


class FixtureRunner:
    """A complete deterministic process boundary; no installed provider runs."""

    def __init__(self, responses, *, root, fingerprint):
        self.responses = dict(responses)
        self.root = root
        self.fingerprint = fingerprint
        self.calls = []

    def __call__(self, argv, **kwargs):
        arguments = tuple(argv[1:])
        self.calls.append((tuple(argv), kwargs))
        response = self.responses.get(arguments)
        if response is None:
            for prefix, candidate in self.responses.items():
                if prefix and prefix[-1] == "*" and arguments[: len(prefix) - 1] == prefix[:-1]:
                    response = candidate
                    break
        if response is None:
            raise AssertionError("unexpected provider argv: %r" % (arguments,))
        if callable(response):
            return response(tuple(argv), kwargs)
        if isinstance(response, Completed):
            return response
        if isinstance(response, Path):
            payload = response.read_text(encoding="utf-8")
        else:
            payload = response
        payload = payload.replace("<PROJECT_ROOT>", str(self.root.resolve()))
        payload = payload.replace("<SOURCE_FINGERPRINT>", self.fingerprint)
        return Completed(payload.encode("utf-8"))


def flatten_argv(calls):
    return " ".join(argument for argv, _ in calls for argument in argv)


def edge_tuples(result):
    nodes = {row["key"]: row["location"] for row in result.nodes}
    return {
        (nodes[row["source"]], nodes[row["target"]], row["kind"])
        for row in result.edges
    }


class GraphAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        temporary = Path(self.temporary.name)
        self.root = temporary / "repo"
        self.root.mkdir()
        for relative, payload in {
            "api/profile.py": 'PROFILE_FIELD = "profile.displayName"\ndef serialize_profile():\n    return PROFILE_FIELD\n',
            "desktop/profile_cache.ts": 'export const cacheKey = "profile.displayName";\n',
            "events/profile_changed.py": 'PROFILE_FIELD = "profile.displayName"\ndef publish_profile_changed():\n    return "profile.changed"\n',
        }.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
        self.bin = temporary / "bin"
        self.bin.mkdir()
        self.executables = {}
        for name in ("sg", "codegraph", "scip", "joern"):
            path = self.bin / name
            path.write_bytes(b"#!/bin/sh\nexit 0\n")
            path.chmod(0o700)
            self.executables[name] = path
        self.clock = FakeClock()
        self.deadline = PROVIDERS.Deadline(self.clock, 30)
        self.seeds = (PROVIDERS_SCAN_SEED("profile.displayName", "api/profile.py"),)
        self.fingerprint = AST_GREP.source_fingerprint(self.root)

    def runner(self, responses):
        return FixtureRunner(responses, root=self.root, fingerprint=self.fingerprint)

    def fixture_text(self, name):
        return (FIXTURES / name).read_text(encoding="utf-8").replace(
            "<PROJECT_ROOT>", str(self.root.resolve())
        ).replace("<SOURCE_FINGERPRINT>", self.fingerprint)

    def prepare_joern_graph(self, creator_version="4.0.12"):
        graph_dir = self.root / ".joern"
        graph_dir.mkdir(exist_ok=True)
        (graph_dir / "cpg.bin").write_bytes(b"JOERN\x00fixture")
        (graph_dir / "metadata.json").write_text(json.dumps({
            "schemaVersion": 1,
            "projectRoot": str(self.root.resolve()),
            "sourceFingerprint": self.fingerprint,
            "createdBy": {"name": "joern", "version": creator_version},
        }), encoding="utf-8")

    def test_ast_grep_045_help_contract_and_stream_query_are_structural_only(self):
        runner = self.runner({
            ("--version",): "ast-grep 0.45.1\n",
            ("--help",): "Usage: sg --json=<STYLE> --lang <LANG> --pattern <PATTERN> <PATH>\n  STYLE: pretty|stream|compact\n",
            ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "api/profile.py"): "",
            ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "events/profile_changed.py"):
                FIXTURES / "ast-grep-query.json",
        })
        spec = PROVIDERS.ProviderSpec("ast-grep", self.executables["sg"])
        probe = AST_GREP.probe(spec, self.root, self.deadline, runner)
        result = AST_GREP.query(probe, self.seeds, self.deadline, runner)
        self.assertEqual(probe.status, "ready")
        self.assertEqual(probe.confidence, "structural-inferred")
        self.assertEqual(probe.repo_root, self.root.resolve())
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.confidence, "structural-inferred")
        self.assertTrue(all(row["confidence"] == "structural-inferred" for row in result.edges))
        self.assertIn(("api/profile.py", "events/profile_changed.py", "references"), edge_tuples(result))
        self.assertEqual(len(result.raw_receipt_sha256), 2)

    def test_ast_grep_rejects_unsupported_version_help_and_shape_drift(self):
        spec = PROVIDERS.ProviderSpec("ast-grep", self.executables["sg"])
        old = self.runner({("--version",): "ast-grep 0.44.9\n", ("--help",): "--json --lang --pattern\n"})
        self.assertEqual(AST_GREP.probe(spec, self.root, self.deadline, old).status, "unsupported")

        runner = self.runner({
            ("--version",): "ast-grep 0.45.1\n",
            ("--help",): "Usage: sg --json=stream --lang <LANG> --pattern <PATTERN> <PATH>\n",
            ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "api/profile.py"):
                '{"file":"../secret","text":"x"}\n',
        })
        probe = AST_GREP.probe(spec, self.root, self.deadline, runner)
        self.assertEqual(AST_GREP.query(probe, self.seeds, self.deadline, runner).status, "failed")

    def test_ast_grep_requires_help_confirmed_json_stream_style(self):
        spec = PROVIDERS.ProviderSpec("ast-grep", self.executables["sg"])
        runner = self.runner({
            ("--version",): "ast-grep 0.45.1\n",
            ("--help",): "--json --lang <LANG> --pattern <PATTERN>\n",
        })
        self.assertEqual(AST_GREP.probe(spec, self.root, self.deadline, runner).status, "unsupported")

    def test_ast_grep_rejects_provider_language_mismatch(self):
        spec = PROVIDERS.ProviderSpec("ast-grep", self.executables["sg"])
        payload = (FIXTURES / "ast-grep-query.json").read_text(encoding="utf-8").replace('"language":"Python"', '"language":"TypeScript"')
        runner = self.runner({
            ("--version",): "ast-grep 0.45.1\n",
            ("--help",): "Usage: sg --json=stream --lang <LANG> --pattern <PATTERN> <PATH>\n",
            ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "api/profile.py"): "",
            ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "events/profile_changed.py"): payload,
        })
        probe = AST_GREP.probe(spec, self.root, self.deadline, runner)
        self.assertEqual(AST_GREP.query(probe, self.seeds, self.deadline, runner).status, "failed")

    def test_ast_grep_binds_range_bytes_lines_counts_text_and_queried_file(self):
        base = json.loads((FIXTURES / "ast-grep-query.json").read_text(encoding="utf-8"))
        mutations = {
            "out-of-file": lambda row: row["range"]["start"].update(line=99),
            "byte-character-mismatch": lambda row: row["range"]["byteOffset"].update(start=16),
            "wrong-lines": lambda row: row.update(lines="different source"),
            "wrong-char-count": lambda row: row["charCount"].update(leading=16),
            "wrong-location": lambda row: row.update(file="api/profile.py"),
        }
        spec = PROVIDERS.ProviderSpec("ast-grep", self.executables["sg"])
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                row = json.loads(json.dumps(base))
                mutate(row)
                runner = self.runner({
                    ("--version",): "ast-grep 0.45.1\n",
                    ("--help",): "Usage: sg --json=stream --lang <LANG> --pattern <PATTERN> <PATH>\n",
                    ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "api/profile.py"): "",
                    ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "events/profile_changed.py"): json.dumps(row),
                })
                probe = AST_GREP.probe(spec, self.root, self.deadline, runner)
                self.assertEqual(AST_GREP.query(probe, self.seeds, self.deadline, runner).status, "failed")

    def test_ast_grep_requires_executable_digest_and_rejects_query_mismatch(self):
        manual = PROVIDERS.ProviderProbe(
            "ast-grep", "ready", "structural-inferred", self.executables["sg"],
            repo_root=self.root, metadata={"source_fingerprint": self.fingerprint},
        )
        never = self.runner({})
        self.assertEqual(AST_GREP.query(manual, self.seeds, self.deadline, never).status, "unsafe")
        self.assertEqual(never.calls, [])

        runner = self.runner({
            ("--version",): "ast-grep 0.45.1\n",
            ("--help",): "Usage: sg --json=stream --lang <LANG> --pattern <PATTERN> <PATH>\n",
        })
        spec = PROVIDERS.ProviderSpec("ast-grep", self.executables["sg"])
        probe = AST_GREP.probe(spec, self.root, self.deadline, runner)
        self.executables["sg"].write_bytes(b"#!/bin/sh\n# changed\nexit 0\n")
        self.executables["sg"].chmod(0o700)
        query_runner = self.runner({
            ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "api/profile.py"): "",
        })
        self.assertEqual(AST_GREP.query(probe, self.seeds, self.deadline, query_runner).status, "unsafe")

    def test_ast_grep_inventory_is_explicit_bounded_and_excludes_ignored_trees(self):
        for relative in (
            "node_modules/hidden.py", "vendor/hidden.py", "generated/hidden.py",
            ".requirements-impact-refiner/hidden.py",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("profile.displayName\n", encoding="utf-8")
        runner = self.runner({
            ("--version",): "ast-grep 0.45.1\n",
            ("--help",): "Usage: sg --json=stream --lang <LANG> --pattern <PATTERN> <PATH>\n",
            ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "api/profile.py"): "",
            ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "events/profile_changed.py"): "",
        })
        spec = PROVIDERS.ProviderSpec("ast-grep", self.executables["sg"])
        probe = AST_GREP.probe(spec, self.root, self.deadline, runner)
        result = AST_GREP.query(probe, self.seeds, self.deadline, runner)
        self.assertEqual(result.status, "ready")
        query_paths = [argv[-1] for argv, _ in runner.calls if "--json=stream" in argv]
        self.assertEqual(query_paths, ["api/profile.py", "events/profile_changed.py"])
        self.assertNotIn(".", query_paths)

        for index in range(501):
            (self.root / ("cap-%03d.py" % index)).write_text("x\n", encoding="utf-8")
        capped = self.runner({
            ("--version",): "ast-grep 0.45.1\n",
            ("--help",): "Usage: sg --json=stream --lang <LANG> --pattern <PATTERN> <PATH>\n",
        })
        self.assertEqual(AST_GREP.probe(spec, self.root, self.deadline, capped).status, "unsafe")
        self.assertFalse(any("--json=stream" in argv for argv, _ in capped.calls))

        oversized_root = Path(self.temporary.name) / "oversized-repo"
        oversized_root.mkdir()
        (oversized_root / "too-large.py").write_bytes(b"x" * (1_048_576 + 1))
        oversized = FixtureRunner({
            ("--version",): "ast-grep 0.45.1\n",
            ("--help",): "Usage: sg --json=stream --lang <LANG> --pattern <PATTERN> <PATH>\n",
        }, root=oversized_root, fingerprint="0" * 64)
        self.assertEqual(AST_GREP.probe(spec, oversized_root, self.deadline, oversized).status, "unsafe")
        self.assertFalse(any("--json=stream" in argv for argv, _ in oversized.calls))

    def test_codegraph_requires_verified_local_fresh_exact_root_status(self):
        runner = self._codegraph_runner()
        spec = PROVIDERS.ProviderSpec("codegraph", self.executables["codegraph"])
        probe = CODEGRAPH.probe(spec, self.root, self.deadline, runner)
        self.assertEqual(probe.status, "ready")
        self.assertEqual(probe.confidence, "verified-provider")
        self.assertEqual(probe.metadata["license"], "Apache-2.0")
        status_call = next(kwargs for argv, kwargs in runner.calls if argv[1:] == ("status", "--json"))
        self.assertEqual(status_call["env"]["CODEGRAPH_TELEMETRY"], "0")

        mismatched = self._codegraph_runner(project_root=str(self.root / "other"))
        self.assertEqual(CODEGRAPH.probe(spec, self.root, self.deadline, mismatched).status, "unsupported")
        stale = self._codegraph_runner(fingerprint="0" * 64)
        self.assertEqual(CODEGRAPH.probe(spec, self.root, self.deadline, stale).status, "stale")

    def _codegraph_runner(self, *, project_root="<PROJECT_ROOT>", fingerprint="<SOURCE_FINGERPRINT>"):
        status = json.dumps({
            "schemaVersion": 1,
            "project": {"root": project_root, "sourceFingerprint": fingerprint, "fresh": True, "local": True},
            "license": {"spdx": "Apache-2.0", "verified": True},
            "provenance": {"channel": "local-cli", "artifact": "codegraph", "verified": True},
        })
        return self.runner({
            ("--version",): "CodeGraph 1.4.2\n",
            ("--help",): "Commands:\n  status\n  explore\n",
            ("status", "--help"): "Usage: codegraph status --json\n",
            ("explore", "--help"): "Usage: codegraph explore --json --seed <TEXT>\n",
            ("status", "--json"): status,
            ("explore", "--json", "--seed", "profile.displayName"):
                FIXTURES / "codegraph-explore.json",
        })

    def test_codegraph_explore_deduplicates_edges_and_preserves_source_ranges(self):
        runner = self._codegraph_runner()
        spec = PROVIDERS.ProviderSpec("codegraph", self.executables["codegraph"])
        probe = CODEGRAPH.probe(spec, self.root, self.deadline, runner)
        result = CODEGRAPH.query(probe, self.seeds, self.deadline, runner)
        self.assertEqual(len(result.edges), 1)
        self.assertEqual(result.edges[0]["confidence"], "verified-provider")
        self.assertIn("1:26-1:45", result.edges[0]["evidence"])
        self.assertIn(("api/profile.py", "desktop/profile_cache.ts", "references"), edge_tuples(result))

    def test_codegraph_rejects_out_of_file_wrong_location_and_excerpt_ranges(self):
        spec = PROVIDERS.ProviderSpec("codegraph", self.executables["codegraph"])
        base = json.loads(self.fixture_text("codegraph-explore.json"))
        mutations = {
            "out-of-file": lambda value: value["edges"][0].update(range=[99, 0, 99, 1]),
            "wrong-location": lambda value: value["edges"][0].update(range=[0, 0, 0, 19]),
            "byte-character-mismatch": lambda value: value["edges"][0].update(excerpt="profile.displayNam"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                value = json.loads(json.dumps(base))
                mutate(value)
                runner = self._codegraph_runner()
                runner.responses[("explore", "--json", "--seed", "profile.displayName")] = json.dumps(value)
                probe = CODEGRAPH.probe(spec, self.root, self.deadline, runner)
                self.assertEqual(CODEGRAPH.query(probe, self.seeds, self.deadline, runner).status, "failed")

    def test_semantic_adapters_reject_utf8_byte_columns_used_as_codepoint_columns(self):
        desktop = self.root / "desktop/profile_cache.ts"
        original_desktop = desktop.read_text(encoding="utf-8")
        desktop.write_text("π" + original_desktop, encoding="utf-8")
        self.fingerprint = AST_GREP.source_fingerprint(self.root)

        codegraph_value = json.loads(self.fixture_text("codegraph-explore.json"))
        for row in (codegraph_value["nodes"][1], *codegraph_value["edges"]):
            row["range"] = [0, 27, 0, 46]
        codegraph_runner = self._codegraph_runner()
        codegraph_runner.responses[("explore", "--json", "--seed", "profile.displayName")] = json.dumps(codegraph_value)
        codegraph_probe = CODEGRAPH.probe(
            PROVIDERS.ProviderSpec("codegraph", self.executables["codegraph"]),
            self.root, self.deadline, codegraph_runner,
        )
        self.assertEqual(CODEGRAPH.query(codegraph_probe, self.seeds, self.deadline, codegraph_runner).status, "failed")

        index = self.root / "index.scip"
        index.write_bytes(b"SCIP\x00fixture")
        scip_value = json.loads(self.fixture_text("scip-print.json"))
        for row in scip_value["documents"][1]["occurrences"]:
            row["range"] = [0, 27, 0, 46]
        scip_probe = SCIP.probe(
            PROVIDERS.ProviderSpec("scip", self.executables["scip"]),
            self.root, self.deadline, self._scip_runner(json.dumps(scip_value)),
        )
        self.assertEqual(scip_probe.status, "failed")

        desktop.write_text(original_desktop, encoding="utf-8")
        events = self.root / "events/profile_changed.py"
        lines = events.read_text(encoding="utf-8").splitlines()
        lines[1] = "π" + lines[1]
        events.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.fingerprint = AST_GREP.source_fingerprint(self.root)
        self.prepare_joern_graph()
        joern_value = json.loads(self.fixture_text("joern-query.json"))
        joern_value["nodes"][1]["range"] = [1, 6, 1, 29]
        joern_value["edges"][0]["range"] = [1, 6, 1, 29]
        joern_runner = self._joern_runner()
        joern_probe = JOERN.probe(
            PROVIDERS.ProviderSpec("joern", self.executables["joern"]),
            self.root, self.deadline, joern_runner,
        )
        joern_runner.responses[("query", "--json", "--graph", ".joern/cpg.bin", "--seed", "profile.displayName")] = json.dumps(joern_value)
        self.assertEqual(JOERN.query(joern_probe, self.seeds, self.deadline, joern_runner).status, "failed")

    def test_semantic_adapters_reject_misleading_help_mentions(self):
        codegraph = self.runner({
            ("--version",): "CodeGraph 1.4.2\n",
            ("--help",): "status and explore are mentioned but unavailable\n",
        })
        self.assertEqual(CODEGRAPH.probe(
            PROVIDERS.ProviderSpec("codegraph", self.executables["codegraph"]),
            self.root, self.deadline, codegraph,
        ).status, "unsupported")

        (self.root / "index.scip").write_bytes(b"SCIP fixture")
        scip = self.runner({
            ("--version",): "scip version 0.6.1\n",
            ("--help",): "print is discussed but not installed\n",
        })
        self.assertEqual(SCIP.probe(
            PROVIDERS.ProviderSpec("scip", self.executables["scip"]),
            self.root, self.deadline, scip,
        ).status, "unsupported")

        self.prepare_joern_graph()
        joern = self.runner({
            ("--version",): "Joern 4.0.12\n",
            ("--help",): "query --json --graph --seed are unrelated words\n",
        })
        self.assertEqual(JOERN.probe(
            PROVIDERS.ProviderSpec("joern", self.executables["joern"]),
            self.root, self.deadline, joern,
        ).status, "unsupported")

    def test_scip_print_json_maps_definitions_and_references(self):
        index = self.root / "index.scip"
        index.write_bytes(b"SCIP\x00fixture")
        runner = self._scip_runner()
        spec = PROVIDERS.ProviderSpec("scip", self.executables["scip"])
        probe = SCIP.probe(spec, self.root, self.deadline, runner)
        result = SCIP.query(probe, self.seeds, self.deadline, runner)
        self.assertEqual(probe.status, "ready")
        self.assertEqual(probe.metadata["indexer"], "scip-python 0.6.10")
        self.assertIn(("api/profile.py", "desktop/profile_cache.ts", "references"), edge_tuples(result))
        self.assertEqual(len(result.edges), 1)
        self.assertEqual(result.edges[0]["confidence"], "verified-provider")
        self.assertRegex(probe.metadata["index_sha256"], r"^[0-9a-f]{64}$")
        print_paths = [argv[-1] for argv, _ in runner.calls if argv[1:3] == ("print", "--json")]
        self.assertTrue(print_paths)
        self.assertTrue(all(Path(path).is_absolute() and path != str(index) for path in print_paths))

    def _scip_runner(self, fixture=None):
        fixture = fixture or FIXTURES / "scip-print.json"
        return self.runner({
            ("--version",): "scip version 0.6.1\n",
            ("--help",): "Commands:\n  print\n",
            ("print", "--help"): "Usage: scip print --json <index>\n",
            ("print", "--json", "*"): fixture,
        })

    def test_scip_missing_symlink_stale_and_shape_drift_never_index_or_upload(self):
        spec = PROVIDERS.ProviderSpec("scip", self.executables["scip"])
        missing_runner = self._scip_runner()
        self.assertEqual(SCIP.probe(spec, self.root, self.deadline, missing_runner).status, "stale")
        self.assertNotIn(" index ", " " + flatten_argv(missing_runner.calls) + " ")

        index = self.root / "index.scip"
        os.symlink(self.root / "api/profile.py", index)
        linked_runner = self._scip_runner()
        self.assertEqual(SCIP.probe(spec, self.root, self.deadline, linked_runner).status, "unsafe")
        index.unlink()
        index.write_bytes(b"SCIP fixture")
        drift = self._scip_runner(fixture='{"metadata":{},"documents":"wrong"}')
        probe = SCIP.probe(spec, self.root, self.deadline, drift)
        self.assertEqual(probe.status, "failed")
        self.assertNotIn("upload", flatten_argv(drift.calls))

    def test_scip_rejects_out_of_file_wrong_location_and_excerpt_ranges(self):
        index = self.root / "index.scip"
        index.write_bytes(b"SCIP\x00fixture")
        spec = PROVIDERS.ProviderSpec("scip", self.executables["scip"])
        base = json.loads(self.fixture_text("scip-print.json"))
        mutations = {
            "out-of-file": lambda value: value["documents"][1]["occurrences"][0].update(range=[99, 0, 99, 1]),
            "wrong-location": lambda value: value["documents"][1]["occurrences"][0].update(range=[0, 0, 0, 19]),
            "byte-character-mismatch": lambda value: value["documents"][1]["occurrences"][0].update(excerpt="profile.displayNam"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                value = json.loads(json.dumps(base))
                mutate(value)
                probe = SCIP.probe(spec, self.root, self.deadline, self._scip_runner(fixture=json.dumps(value)))
                self.assertEqual(probe.status, "failed")

    def test_scip_index_atomic_replacement_and_same_inode_mutation_fail_stale(self):
        index = self.root / "index.scip"
        index.write_bytes(b"SCIP\x00fixture")
        spec = PROVIDERS.ProviderSpec("scip", self.executables["scip"])
        payload = self.fixture_text("scip-print.json").encode("utf-8")

        for mode in ("replace", "same-inode"):
            with self.subTest(mode=mode):
                index.write_bytes(b"SCIP\x00fixture")
                probe = SCIP.probe(spec, self.root, self.deadline, self._scip_runner())
                self.assertEqual(probe.status, "ready")
                seen = []
                def mutate(argv, kwargs):
                    snapshot = Path(argv[-1])
                    seen.append(snapshot)
                    self.assertNotEqual(snapshot, index)
                    self.assertEqual(snapshot.read_bytes(), b"SCIP\x00fixture")
                    if mode == "replace":
                        replacement = self.root / "replacement.scip"
                        replacement.write_bytes(b"SCIP replacement")
                        os.replace(replacement, index)
                    else:
                        with index.open("r+b") as handle:
                            handle.seek(0)
                            handle.write(b"MUTATED SAME")
                            handle.flush()
                            os.fsync(handle.fileno())
                    return Completed(payload)
                runner = self.runner({("print", "--json", "*"): mutate})
                result = SCIP.query(probe, self.seeds, self.deadline, runner)
                self.assertEqual(result.status, "stale")
                self.assertTrue(seen)
                self.assertTrue(all(not snapshot.exists() for snapshot in seen))

    def test_joern_never_cold_parses_without_existing_fresh_graph(self):
        spec = PROVIDERS.ProviderSpec("joern", self.executables["joern"])
        runner = self._joern_runner()
        probe = JOERN.probe(spec, self.root, self.deadline, runner)
        self.assertEqual(probe.status, "stale")
        self.assertNotIn("joern-parse", flatten_argv(runner.calls))
        self.assertNotIn("server", flatten_argv(runner.calls))

    def _joern_runner(self, *, fingerprint="<SOURCE_FINGERPRINT>"):
        return self.runner({
            ("--version",): "Joern 4.0.12\n",
            ("--help",): "Usage: joern query --json --graph <GRAPH> --seed <TEXT>\n",
            ("query", "--help"): "Usage: joern query --json --graph <GRAPH> --seed <TEXT>\n",
            ("query", "--json", "--graph", ".joern/cpg.bin", "--seed", "profile.displayName"):
                FIXTURES / "joern-query.json",
        })

    def test_joern_queries_only_existing_local_graph_with_matching_fingerprint(self):
        self.prepare_joern_graph()
        graph_dir = self.root / ".joern"
        runner = self._joern_runner()
        spec = PROVIDERS.ProviderSpec("joern", self.executables["joern"])
        probe = JOERN.probe(spec, self.root, self.deadline, runner)
        result = JOERN.query(probe, self.seeds, self.deadline, runner)
        self.assertEqual(probe.status, "ready")
        self.assertIn(("api/profile.py", "events/profile_changed.py", "calls"), edge_tuples(result))
        self.assertTrue(all(row["confidence"] == "verified-provider" for row in result.edges))

        metadata = json.loads((graph_dir / "metadata.json").read_text(encoding="utf-8"))
        metadata["sourceFingerprint"] = "0" * 64
        (graph_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        stale = JOERN.probe(spec, self.root, self.deadline, self._joern_runner())
        self.assertEqual(stale.status, "stale")

    def test_joern_creator_version_is_valid_and_exact_not_empty_or_substring(self):
        spec = PROVIDERS.ProviderSpec("joern", self.executables["joern"])
        for creator in ("", "4.0.1", "not-4.0.12"):
            with self.subTest(creator=creator):
                self.prepare_joern_graph(creator)
                probe = JOERN.probe(spec, self.root, self.deadline, self._joern_runner())
                expected = "unsupported" if creator == "4.0.1" else "failed"
                self.assertEqual(probe.status, expected)

    def test_joern_rejects_out_of_file_wrong_location_and_excerpt_ranges(self):
        self.prepare_joern_graph()
        spec = PROVIDERS.ProviderSpec("joern", self.executables["joern"])
        base = json.loads(self.fixture_text("joern-query.json"))
        mutations = {
            "out-of-file": lambda value: value["edges"][0].update(range=[99, 0, 99, 1]),
            "wrong-location": lambda value: value["edges"][0].update(range=[0, 0, 0, 19]),
            "byte-character-mismatch": lambda value: value["edges"][0].update(excerpt="publish_profile_change"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                value = json.loads(json.dumps(base))
                mutate(value)
                runner = self._joern_runner()
                probe = JOERN.probe(spec, self.root, self.deadline, runner)
                runner.responses[("query", "--json", "--graph", ".joern/cpg.bin", "--seed", "profile.displayName")] = json.dumps(value)
                self.assertEqual(JOERN.query(probe, self.seeds, self.deadline, runner).status, "failed")

    def test_all_adapters_propagate_runner_truncation_without_parsing(self):
        (self.root / "index.scip").write_bytes(b"SCIP fixture")
        graph_dir = self.root / ".joern"
        graph_dir.mkdir()
        graph = graph_dir / "cpg.bin"
        graph.write_bytes(b"JOERN fixture")
        (graph_dir / "metadata.json").write_text("{}", encoding="utf-8")
        index_identity = SCIP._index_observation(self.root)
        modules = (
            (AST_GREP, "ast-grep", "sg"),
            (CODEGRAPH, "codegraph", "codegraph"),
            (SCIP, "scip", "scip"),
            (JOERN, "joern", "joern"),
        )
        for module, provider, executable in modules:
            with self.subTest(provider=provider):
                probe = PROVIDERS.ProviderProbe(
                    provider, "ready",
                    "structural-inferred" if provider == "ast-grep" else "verified-provider",
                    self.executables[executable],
                    executable_sha256=hashlib.sha256(self.executables[executable].read_bytes()).hexdigest(),
                    repo_root=self.root,
                    metadata={
                        "index": "index.scip", "graph": ".joern/cpg.bin",
                        "source_fingerprint": self.fingerprint,
                        "graph_sha256": hashlib.sha256(graph.read_bytes()).hexdigest(),
                        "index_sha256": index_identity["sha256"],
                        "index_identity": index_identity,
                    },
                )
                runner = self.runner({
                    ("--json=stream", "--lang", "python", "--pattern", "profile.displayName", "api/profile.py"):
                        Completed(b"{}", stdout_truncated=True),
                    ("explore", "--json", "--seed", "profile.displayName"):
                        Completed(b"{}", stdout_truncated=True),
                    ("print", "--json", "*"):
                        Completed(b"{}", stdout_truncated=True),
                    ("query", "--json", "--graph", ".joern/cpg.bin", "--seed", "profile.displayName"):
                        Completed(b"{}", stdout_truncated=True),
                })
                self.assertEqual(module.query(probe, self.seeds, self.deadline, runner).status, "failed")

    def test_no_adapter_argv_contains_mutating_or_network_commands(self):
        forbidden = {"install", "update", "auth", "login", "upload", "index", "parse", "server", "watch"}
        observed = []
        ast = self.runner({
            ("--version",): "ast-grep 0.45.1\n",
            ("--help",): "Usage: sg --json=stream --lang <LANG> --pattern <PATTERN> <PATH>\n",
        })
        AST_GREP.probe(PROVIDERS.ProviderSpec("ast-grep", self.executables["sg"]), self.root, self.deadline, ast)
        observed.extend(ast.calls)
        codegraph = self._codegraph_runner()
        CODEGRAPH.probe(PROVIDERS.ProviderSpec("codegraph", self.executables["codegraph"]), self.root, self.deadline, codegraph)
        observed.extend(codegraph.calls)
        self.assertTrue(forbidden.isdisjoint(flatten_argv(observed).lower().split()))


# Use the actual immutable seed contract without making adapters depend on coordinator.
BUILTIN = load_module("_rir_graph_builtin", "graph_builtin.py")
PROVIDERS_SCAN_SEED = BUILTIN.ScanSeed


if __name__ == "__main__":
    unittest.main()
