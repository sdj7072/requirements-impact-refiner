import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "requirements-impact-refiner"


class MarketplaceDistributionTest(unittest.TestCase):
    def load(self, relative_path):
        return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))

    def test_codex_marketplace_resolves_the_root_plugin(self):
        marketplace = self.load(".agents/plugins/marketplace.json")
        self.assertEqual(marketplace["name"], PLUGIN_NAME)
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], PLUGIN_NAME)
        self.assertEqual(entry["source"], {"source": "local", "path": "./"})
        self.assertEqual(
            entry["policy"],
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )
        self.assertEqual(entry["category"], "Developer Tools")
        plugin_manifest = (
            ROOT / entry["source"]["path"] / ".codex-plugin/plugin.json"
        )
        self.assertTrue(plugin_manifest.is_file())

    def test_claude_marketplace_resolves_the_root_plugin(self):
        marketplace = self.load(".claude-plugin/marketplace.json")
        self.assertEqual(marketplace["name"], PLUGIN_NAME)
        self.assertEqual(marketplace["owner"]["name"], "sdj7072")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], PLUGIN_NAME)
        self.assertEqual(entry["source"], "./")
        plugin_manifest = ROOT / entry["source"] / ".claude-plugin/plugin.json"
        self.assertTrue(plugin_manifest.is_file())

    def test_marketplaces_match_the_plugin_identity(self):
        codex_plugin = self.load(".codex-plugin/plugin.json")
        claude_plugin = self.load(".claude-plugin/plugin.json")
        codex_entry = self.load(".agents/plugins/marketplace.json")["plugins"][0]
        claude_entry = self.load(".claude-plugin/marketplace.json")["plugins"][0]
        for entry in (codex_entry, claude_entry):
            self.assertEqual(entry["name"], codex_plugin["name"])
        self.assertEqual(claude_entry["version"], codex_plugin["version"])
        self.assertEqual(claude_entry["description"], codex_plugin["description"])
        self.assertEqual(codex_plugin["name"], claude_plugin["name"])


class GenericInstallerTest(unittest.TestCase):
    def run_installer(self, target_dir):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/install-agent-skill.py"),
                "--target-dir",
                str(target_dir),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_installer_copies_the_complete_canonical_skill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir) / ".agents" / "skills"
            result = self.run_installer(target_dir)
            self.assertEqual(result.returncode, 0, result.stderr)

            installed = target_dir / PLUGIN_NAME
            source = ROOT / "skills" / PLUGIN_NAME
            source_files = sorted(
                path.relative_to(source) for path in source.rglob("*") if path.is_file()
            )
            installed_files = sorted(
                path.relative_to(installed)
                for path in installed.rglob("*")
                if path.is_file()
            )
            self.assertEqual(installed_files, source_files)
            for relative_path in source_files:
                self.assertEqual(
                    (installed / relative_path).read_bytes(),
                    (source / relative_path).read_bytes(),
                )

    def test_installer_refuses_to_overwrite_an_existing_skill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir) / ".agents" / "skills"
            first = self.run_installer(target_dir)
            self.assertEqual(first.returncode, 0, first.stderr)
            marker = target_dir / PLUGIN_NAME / "local-marker.txt"
            marker.write_text("preserve me", encoding="utf-8")

            second = self.run_installer(target_dir)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("already exists", second.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me")


if __name__ == "__main__":
    unittest.main()
