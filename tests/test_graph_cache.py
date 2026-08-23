import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "requirements-impact-refiner" / "scripts" / "graph_cache.py"
SPEC = importlib.util.spec_from_file_location("graph_cache", MODULE_PATH)
CACHE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CACHE
SPEC.loader.exec_module(CACHE)


def receipt():
    return {
        "schema_version": 1,
        "receipt_id": "0" * 32,
        "draft_id": "1" * 32,
        "repo_root_sha256": "2" * 64,
        "request_sha256": "3" * 64,
        "settings": {
            "enabled": True, "max_seconds": 30, "target_seconds": 10,
            "providers": ["auto"], "install_policy": "never", "deep": False,
        },
        "providers": [{
            "name": "builtin", "status": "ready", "confidence": "verified-source",
            "version": "builtin-v1", "executable_sha256": "4" * 64,
        }],
        "nodes": [
            {
                "id": "NODE-001", "kind": "api_field", "label": "profile.displayName",
                "location": "api/profile.py", "provider": "builtin", "confidence": "lexical",
                "source_sha256": "a" * 64, "risk_domains": ["interfaces"],
            },
            {
                "id": "NODE-002", "kind": "cache", "label": "profile cache",
                "location": "desktop/profile_cache.ts", "provider": "builtin", "confidence": "lexical",
                "source_sha256": "b" * 64, "risk_domains": ["state/concurrency"],
            },
            {
                "id": "NODE-003", "kind": "test", "label": "profile migration",
                "location": "tests/test_profile_migration.py", "provider": "builtin", "confidence": "lexical",
                "source_sha256": "c" * 64, "risk_domains": ["regression"],
            },
        ],
        "edges": [
            {
                "id": "EDGE-001", "source": "NODE-001", "target": "NODE-002",
                "kind": "caches", "location": "desktop/profile_cache.ts",
                "evidence": "profile.displayName", "confidence": "lexical",
                "provider": "builtin", "source_sha256": "b" * 64,
            },
            {
                "id": "EDGE-002", "source": "NODE-002", "target": "NODE-003",
                "kind": "tests", "location": "tests/test_profile_migration.py",
                "evidence": "CachedProfileDTO", "confidence": "lexical",
                "provider": "builtin", "source_sha256": "c" * 64,
            },
        ],
        "paths": [{
            "id": "PATH-001", "nodes": ["NODE-001", "NODE-002", "NODE-003"],
            "edges": ["EDGE-001", "EDGE-002"], "distance": 2,
            "risk_domains": ["interfaces", "state/concurrency", "regression"],
        }],
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

    def test_missing_source_invalidates_the_node_and_its_dependents(self):
        first = CACHE.publish(self.root, receipt(), digests())
        current = digests()
        del current["desktop/profile_cache.ts"]
        partial = CACHE.load(self.root, first.key, current)
        self.assertEqual(partial.status, "partial")
        self.assertEqual(partial.invalidated_nodes, ("NODE-002", "NODE-003"))

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
        self.assertEqual(CACHE.load(self.root, second.key, {**digests(), "extra.py": "d" * 64}).status, "hit")

        target = second.artifact.with_name("target.json")
        target.write_bytes(second.artifact.read_bytes())
        second.artifact.unlink()
        os.symlink(target, second.artifact)
        self.assertEqual(CACHE.load(self.root, second.key, digests()).status, "miss")

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
        self.assertEqual(set(json.loads(payload)), {
            "cache_schema_version", "identity", "receipt", "source_digests",
        })

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
