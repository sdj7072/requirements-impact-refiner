import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "graph_cache.py"
SPEC = importlib.util.spec_from_file_location("graph_cache", MODULE_PATH)
CACHE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CACHE
SPEC.loader.exec_module(CACHE)
BUILTIN_SPEC = importlib.util.spec_from_file_location(
    "graph_builtin_cache_integration",
    ROOT / "scripts" / "graph_builtin.py",
)
BUILTIN = importlib.util.module_from_spec(BUILTIN_SPEC)
sys.modules[BUILTIN_SPEC.name] = BUILTIN
BUILTIN_SPEC.loader.exec_module(BUILTIN)


class StaticClock:
    def monotonic(self):
        return 0.0


def receipt():
    return {
        "schema_version": 1,
        "receipt_id": "0" * 32,
        "draft_id": "1" * 32,
        "repo_root_sha256": "2" * 64,
        "request_sha256": "3" * 64,
        "settings": {
            "enabled": True,
            "max_seconds": 30,
            "target_seconds": 10,
            "providers": ["auto"],
            "install_policy": "never",
            "deep": False,
        },
        "providers": [
            {
                "name": "builtin",
                "status": "ready",
                "confidence": "verified-source",
                "version": "builtin-v1",
                "executable_sha256": "4" * 64,
            }
        ],
        "nodes": [
            {
                "id": "NODE-001",
                "kind": "api_field",
                "label": "profile.displayName",
                "location": "api/profile.py",
                "provider": "builtin",
                "confidence": "lexical",
                "source_sha256": "a" * 64,
                "risk_domains": ["interfaces"],
            },
            {
                "id": "NODE-002",
                "kind": "cache",
                "label": "profile cache",
                "location": "desktop/profile_cache.ts",
                "provider": "builtin",
                "confidence": "lexical",
                "source_sha256": "b" * 64,
                "risk_domains": ["state/concurrency"],
            },
            {
                "id": "NODE-003",
                "kind": "test",
                "label": "profile migration",
                "location": "tests/test_profile_migration.py",
                "provider": "builtin",
                "confidence": "lexical",
                "source_sha256": "c" * 64,
                "risk_domains": ["regression"],
            },
        ],
        "edges": [
            {
                "id": "EDGE-001",
                "source": "NODE-001",
                "target": "NODE-002",
                "kind": "caches",
                "location": "desktop/profile_cache.ts",
                "evidence": "profile.displayName",
                "confidence": "lexical",
                "provider": "builtin",
                "source_sha256": "b" * 64,
            },
            {
                "id": "EDGE-002",
                "source": "NODE-002",
                "target": "NODE-003",
                "kind": "tests",
                "location": "tests/test_profile_migration.py",
                "evidence": "CachedProfileDTO",
                "confidence": "lexical",
                "provider": "builtin",
                "source_sha256": "c" * 64,
            },
        ],
        "paths": [
            {
                "id": "PATH-001",
                "nodes": ["NODE-001", "NODE-002", "NODE-003"],
                "edges": ["EDGE-001", "EDGE-002"],
                "distance": 2,
                "risk_domains": ["interfaces", "state/concurrency", "regression"],
            }
        ],
        "frontier": [],
        "timings_ms": {"total": 1},
        "budget_status": "closed",
        "cache": {"status": "miss", "key": "5" * 64, "invalidated_nodes": []},
    }


def digests():
    return {
        "api/profile.py": "a" * 64,
        "desktop/profile_cache.ts": "b" * 64,
        "tests/test_profile_migration.py": "c" * 64,
    }


def receipt_from_scan(result):
    return {
        "schema_version": 1,
        "receipt_id": "6" * 32,
        "draft_id": "7" * 32,
        "repo_root_sha256": "8" * 64,
        "request_sha256": "9" * 64,
        "settings": {
            "enabled": True,
            "max_seconds": 30,
            "target_seconds": 10,
            "providers": ["auto"],
            "install_policy": "never",
            "deep": False,
        },
        "providers": [
            {
                "name": "builtin",
                "status": "ready",
                "confidence": "verified-source",
                "version": "builtin-v1",
                "executable_sha256": "4" * 64,
            }
        ],
        "nodes": [
            {
                "id": node.id,
                "kind": node.kind,
                "label": node.label,
                "location": node.location,
                "provider": node.provider,
                "confidence": node.confidence,
                "source_sha256": node.source_sha256,
                "risk_domains": list(node.risk_domains),
            }
            for node in result.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "kind": edge.kind,
                "location": edge.location,
                "evidence": edge.evidence,
                "confidence": edge.confidence,
                "provider": edge.provider,
                "source_sha256": edge.source_sha256,
            }
            for edge in result.edges
        ],
        "paths": [
            {
                "id": path.id,
                "nodes": list(path.nodes),
                "edges": list(path.edges),
                "distance": path.distance,
                "risk_domains": list(path.risk_domains),
            }
            for path in result.paths
        ],
        "frontier": [
            {
                "id": item.id,
                "node": item.node,
                "reason": item.reason,
                "risk_domains": list(item.risk_domains),
            }
            for item in result.frontier
        ],
        "timings_ms": {"total": 1},
        "budget_status": result.budget_status,
        "cache": {"status": "miss", "key": "5" * 64, "invalidated_nodes": []},
    }


class GraphCacheTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def test_cache_reuses_unchanged_nodes_and_invalidates_dependents(self):
        source_digests = digests()
        first = CACHE.publish(self.root, receipt(), source_digests)
        loaded = CACHE.load(self.root, first.key, source_digests)
        self.assertEqual(loaded.status, "hit")
        self.assertEqual(loaded.receipt["nodes"][1]["confidence"], "lexical")

        changed = {**source_digests, "desktop/profile_cache.ts": "f" * 64}
        partial = CACHE.load(self.root, first.key, changed)
        self.assertEqual(partial.status, "partial")
        self.assertEqual(partial.invalidated_nodes, ("NODE-002", "NODE-003"))
        self.assertNotIn("NODE-001", partial.invalidated_nodes)

    def test_cache_publication_never_changes_subsequent_scan_inputs_or_results(self):
        source = self.root / "api"
        source.mkdir()
        (source / "profile.py").write_text('FIELD = "profile.displayName"\n', encoding="utf-8")
        seeds = (BUILTIN.ScanSeed("profile.displayName", "api/profile.py"),)
        limits = BUILTIN.ScanLimits()
        first = BUILTIN.scan_repository(self.root, seeds, limits, StaticClock())

        CACHE.publish(self.root, receipt(), digests())
        second = BUILTIN.scan_repository(self.root, seeds, limits, StaticClock())

        self.assertEqual(second, first)
        self.assertEqual(second.source_digests, first.source_digests)
        self.assertFalse(
            any(
                (node.location or "").startswith(".requirements-impact-refiner/")
                for node in second.nodes
            )
        )

    def test_missing_source_invalidates_the_node_and_its_dependents(self):
        first = CACHE.publish(self.root, receipt(), digests())
        current = digests()
        del current["desktop/profile_cache.ts"]
        partial = CACHE.load(self.root, first.key, current)
        self.assertEqual(partial.status, "partial")
        self.assertEqual(partial.invalidated_nodes, ("NODE-002", "NODE-003"))

    def test_new_unmapped_source_requires_full_rescan(self):
        first = CACHE.publish(self.root, receipt(), digests())
        current = {**digests(), "new/unmapped.py": "d" * 64}

        loaded = CACHE.load(self.root, first.key, current)

        self.assertEqual(loaded.status, "miss")
        self.assertEqual(loaded.invalidated_nodes, ())

        mixed = {
            **current,
            "desktop/profile_cache.ts": "e" * 64,
        }
        self.assertEqual(CACHE.load(self.root, first.key, mixed).status, "miss")

    def test_changed_omitted_source_requires_full_rescan(self):
        cached = {**digests(), "docs/omitted.md": "d" * 64}
        first = CACHE.publish(self.root, receipt(), cached)
        current = {**cached, "docs/omitted.md": "e" * 64}

        loaded = CACHE.load(self.root, first.key, current)

        self.assertEqual(loaded.status, "miss")
        self.assertEqual(loaded.invalidated_nodes, ())

    def test_identity_changes_for_provider_version_config_schema_and_root(self):
        baseline = CACHE.publish(self.root, receipt(), digests())
        provider_changed = receipt()
        provider_changed["providers"][0]["version"] = "builtin-v2"
        configured = receipt()
        configured["settings"]["deep"] = True
        other_root = Path(self.temporary.name) / "other"
        other_root.mkdir()

        keys = {
            baseline.key,
            CACHE.publish(self.root, provider_changed, digests()).key,
            CACHE.publish(self.root, configured, digests()).key,
            CACHE.publish(self.root, receipt(), digests(), schema_version=2).key,
            CACHE.publish(other_root, receipt(), digests()).key,
        }
        self.assertEqual(len(keys), 5)
        self.assertEqual(CACHE.load(other_root, baseline.key, digests()).status, "miss")

    def test_identity_separates_draft_request_and_receipt_on_same_sources(self):
        first_receipt = receipt()
        second_receipt = receipt()
        second_receipt["receipt_id"] = "a" * 32
        second_receipt["draft_id"] = "b" * 32
        second_receipt["request_sha256"] = "c" * 64

        first = CACHE.publish(self.root, first_receipt, digests())
        second = CACHE.publish(self.root, second_receipt, digests())

        self.assertNotEqual(first.key, second.key)
        self.assertEqual(
            CACHE.load(self.root, first.key, digests()).receipt["draft_id"],
            "1" * 32,
        )
        self.assertEqual(
            CACHE.load(self.root, second.key, digests()).receipt["draft_id"],
            "b" * 32,
        )

    def test_incomplete_inventory_is_identity_bound_and_never_reused_as_hit(self):
        incomplete = CACHE.publish(
            self.root,
            receipt(),
            {},
            inventory_complete=False,
            inventory_reason="deadline",
        )
        complete = CACHE.publish(self.root, receipt(), {})

        self.assertNotEqual(incomplete.key, complete.key)
        self.assertEqual(CACHE.load(self.root, incomplete.key, {}).status, "miss")
        payload = json.loads(incomplete.artifact.read_text(encoding="utf-8"))
        self.assertFalse(payload["identity"]["source_inventory_complete"])
        self.assertEqual(payload["identity"]["source_inventory_reason"], "deadline")

    def test_rejects_corrupt_source_digests(self):
        invalid = {**digests(), "api/profile.py": "not-a-digest"}
        with self.assertRaisesRegex(ValueError, "source digest"):
            CACHE.publish(self.root, receipt(), invalid)
        first = CACHE.publish(self.root, receipt(), digests())
        self.assertEqual(CACHE.load(self.root, first.key, invalid).status, "miss")

    def test_malformed_symlink_and_partial_artifacts_fail_closed(self):
        first = CACHE.publish(self.root, receipt(), digests())
        first.artifact.write_text("{malformed", encoding="utf-8")
        self.assertEqual(CACHE.load(self.root, first.key, digests()).status, "miss")

        second = CACHE.publish(self.root, receipt(), {**digests(), "extra.py": "d" * 64})
        partial = second.artifact.with_suffix(".json.tmp")
        partial.write_text("partial", encoding="utf-8")
        self.assertEqual(
            CACHE.load(self.root, second.key, {**digests(), "extra.py": "d" * 64}).status, "hit"
        )

        target = second.artifact.with_name("target.json")
        target.write_bytes(second.artifact.read_bytes())
        second.artifact.unlink()
        os.symlink(target, second.artifact)
        self.assertEqual(CACHE.load(self.root, second.key, digests()).status, "miss")

    def test_cache_schema_version_requires_the_exact_integer_one(self):
        for sentinel, valid in ((True, False), (1.0, False), ("1", False), (1, True)):
            with self.subTest(boundary="publish", sentinel=sentinel):
                if valid:
                    self.assertEqual(
                        CACHE.publish(
                            self.root, receipt(), digests(), schema_version=sentinel
                        ).status,
                        "miss",
                    )
                else:
                    with self.assertRaisesRegex(ValueError, "schema_version"):
                        CACHE.publish(self.root, receipt(), digests(), schema_version=sentinel)

        published = CACHE.publish(self.root, receipt(), digests())
        baseline = json.loads(published.artifact.read_text(encoding="utf-8"))
        for sentinel, expected in ((True, "miss"), (1.0, "miss"), ("1", "miss"), (1, "hit")):
            with self.subTest(boundary="load", sentinel=sentinel):
                payload = dict(baseline)
                payload["cache_schema_version"] = sentinel
                published.artifact.write_text(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8",
                )

                self.assertEqual(CACHE.load(self.root, published.key, digests()).status, expected)

    def test_unhashable_inventory_reason_and_graph_fields_are_cache_misses(self):
        incomplete = CACHE.publish(
            self.root,
            receipt(),
            digests(),
            inventory_complete=False,
            inventory_reason="deadline",
        )
        baseline = json.loads(incomplete.artifact.read_text(encoding="utf-8"))
        cases = (
            (("identity", "source_inventory_reason"), []),
            (("identity", "source_inventory_reason"), {}),
            (("receipt", "nodes", 0, "kind"), []),
            (("receipt", "cache", "status"), {}),
        )
        for path, malformed in cases:
            with self.subTest(path=path, malformed=malformed):
                payload = json.loads(json.dumps(baseline))
                target = payload
                for component in path[:-1]:
                    target = target[component]
                target[path[-1]] = malformed
                incomplete.artifact.write_text(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8",
                )

                self.assertEqual(CACHE.load(self.root, incomplete.key, digests()).status, "miss")

    def test_over_deep_cache_json_is_rejected_before_decoder_invocation(self):
        published = CACHE.publish(self.root, receipt(), digests())
        published.artifact.write_text("[" * 65 + "0" + "]" * 65, encoding="utf-8")

        with mock.patch.object(
            CACHE.json,
            "loads",
            side_effect=AssertionError("over-deep JSON reached the decoder"),
        ):
            loaded = CACHE.load(self.root, published.key, digests())

        self.assertEqual(loaded.status, "miss")

    def test_receipt_cannot_diverge_from_the_keyed_identity(self):
        published = CACHE.publish(self.root, receipt(), digests())
        payload = json.loads(published.artifact.read_text(encoding="utf-8"))
        payload["receipt"]["settings"]["deep"] = True
        published.artifact.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

        self.assertEqual(CACHE.load(self.root, published.key, digests()).status, "miss")

    def test_publish_uses_atomic_private_artifact_and_pointer(self):
        first = CACHE.publish(self.root, receipt(), digests())
        cache_dir = self.root / ".requirements-impact-refiner" / "cache" / "graph" / "v1"
        pointer = cache_dir / "current"
        self.assertEqual(pointer.read_text(encoding="ascii"), first.key + "\n")
        self.assertEqual(stat.S_IMODE(first.artifact.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(pointer.stat().st_mode), 0o600)
        self.assertEqual(list(cache_dir.glob("*.tmp")), [])

        second_receipt = receipt()
        second_receipt["settings"]["deep"] = True
        second = CACHE.publish(self.root, second_receipt, digests())
        self.assertNotEqual(first.key, second.key)
        self.assertEqual(pointer.read_text(encoding="ascii"), second.key + "\n")

    def test_never_persists_credentials_or_environment(self):
        secret = "cache-must-not-persist-this-secret"
        with mock.patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": secret}, clear=False):
            published = CACHE.publish(self.root, receipt(), digests())
        payload = published.artifact.read_bytes()
        self.assertNotIn(secret.encode("ascii"), payload)
        self.assertNotIn(b"AWS_SECRET_ACCESS_KEY", payload)
        self.assertEqual(
            set(json.loads(payload)),
            {
                "cache_schema_version",
                "identity",
                "receipt",
                "source_digests",
            },
        )

    def test_secret_source_literals_never_enter_graph_or_serialized_cache(self):
        secret = "sk-live-duplicated-super-secret-123456789"
        fixtures = {
            "api.py": f'MARKER = "credentialRotation"\nAPI_KEY = "{secret}"\n',
            "worker.py": f'MARKER = "credentialRotation"\nPASSWORD = "{secret}"\n',
            "events.py": f'MARKER = "credentialRotation"\nTOKEN = "{secret}"\n',
        }
        for relative, text in fixtures.items():
            (self.root / relative).write_text(text, encoding="utf-8")
        result = BUILTIN.scan_repository(
            self.root,
            (BUILTIN.ScanSeed("credentialRotation", "api.py"),),
            BUILTIN.ScanLimits(),
            StaticClock(),
        )

        self.assertNotIn(secret, repr(result))
        published = CACHE.publish(self.root, receipt_from_scan(result), result.source_digests)

        self.assertNotIn(secret.encode("utf-8"), published.artifact.read_bytes())

    def test_secret_key_contexts_redact_ordinary_values_across_config_syntaxes(self):
        cases = {
            "aws_python": (
                ".py",
                'AWS_SECRET_ACCESS_KEY = "{value}"\nMARKER = "credentialRotation"\n',
            ),
            "client_json": (".json", '{{"client_secret":"{value}","marker":"credentialRotation"}}'),
            "access_yaml": (".yaml", 'access-token: "{value}"\nmarker: "credentialRotation"\n'),
            "refresh_env": (".env", "REFRESH_TOKEN={value}\nMARKER=credentialRotation\n"),
            "password_python": (".py", 'password = "{value}"\nmarker = "credentialRotation"\n'),
            "passwd_yaml": (".yaml", 'passwd: "{value}"\nmarker: "credentialRotation"\n'),
            "private_json": (".json", '{{"private_key":"{value}","marker":"credentialRotation"}}'),
            "api_env": (".env", "API_KEY={value}\nMARKER=credentialRotation\n"),
            "secret_json": (".json", '{{"secret":"{value}","marker":"credentialRotation"}}'),
            "credential_yaml": (".yaml", 'credential: "{value}"\nmarker: "credentialRotation"\n'),
            "token_env": (".env", "TOKEN={value}\nMARKER=credentialRotation\n"),
            "token_yaml": (".yaml", 'token: "{value}"\nmarker: "credentialRotation"\n'),
            "token_json": (".json", '{{"token":"{value}","marker":"credentialRotation"}}'),
            "token_python": (".py", 'token = "{value}"\nmarker = "credentialRotation"\n'),
        }
        for index, (name, (suffix, template)) in enumerate(cases.items()):
            with self.subTest(name=name):
                case_root = self.root / name
                case_root.mkdir()
                raw = f"ordinary{name.title().replace('_', '')}ValueForImpact"
                for stem in ("source_a", "source_b"):
                    (case_root / f"{stem}{suffix}").write_text(
                        template.format(value=raw), encoding="utf-8"
                    )
                result = BUILTIN.scan_repository(
                    case_root,
                    (BUILTIN.ScanSeed("credentialRotation", f"source_a{suffix}"),),
                    BUILTIN.ScanLimits(),
                    StaticClock(),
                )

                self.assertIn("credentialRotation", {node.label for node in result.nodes})
                self.assertNotIn(raw, repr(result))
                self.assertTrue(all(raw not in node.label for node in result.nodes))
                self.assertTrue(all(raw not in edge.evidence for edge in result.edges))
                published = CACHE.publish(
                    case_root,
                    receipt_from_scan(result),
                    result.source_digests,
                    schema_version=index + 1,
                )
                self.assertNotIn(raw.encode("utf-8"), published.artifact.read_bytes())

        innocent_root = self.root / "innocent_symbol"
        innocent_root.mkdir()
        innocent = "ordinaryLongSharedDomainSymbolWithoutCredentialContext"
        for stem in ("source_a.py", "source_b.py"):
            (innocent_root / stem).write_text(f'MESSAGE = "{innocent}"\n', encoding="utf-8")
        innocent_result = BUILTIN.scan_repository(
            innocent_root,
            (BUILTIN.ScanSeed(innocent, "source_a.py"),),
            BUILTIN.ScanLimits(),
            StaticClock(),
        )
        self.assertIn(innocent, {node.label for node in innocent_result.nodes})
        self.assertIn(innocent, {edge.evidence for edge in innocent_result.edges})

        token_root = self.root / "standalone_token_identifier"
        token_root.mkdir()
        for stem in ("source_a.py", "source_b.py"):
            (token_root / stem).write_text("token\n", encoding="utf-8")
        token_result = BUILTIN.scan_repository(
            token_root,
            (BUILTIN.ScanSeed("token", "source_a.py"),),
            BUILTIN.ScanLimits(),
            StaticClock(),
        )
        self.assertIn("token", {node.label for node in token_result.nodes})
        self.assertIn("token", {edge.evidence for edge in token_result.edges})

    def test_rejects_symlinked_cache_components(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        control = self.root / ".requirements-impact-refiner"
        control.mkdir()
        os.symlink(outside, control / "cache")
        with self.assertRaisesRegex(ValueError, "symlink"):
            CACHE.publish(self.root, receipt(), digests())


if __name__ == "__main__":
    unittest.main()
