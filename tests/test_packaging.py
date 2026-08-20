import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_COMPONENTS = {"mcpServers", "apps", "hooks", "agents", "dependencies"}


class PackagingTest(unittest.TestCase):
    def load(self, relative_path):
        return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))

    def test_canonical_skill_exists(self):
        self.assertTrue(
            (ROOT / "skills/requirements-impact-refiner/SKILL.md").is_file()
        )

    def test_codex_manifest_points_to_canonical_skills(self):
        manifest = self.load(".codex-plugin/plugin.json")
        self.assertEqual(manifest["name"], "requirements-impact-refiner")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertTrue(FORBIDDEN_COMPONENTS.isdisjoint(manifest))

    def test_claude_manifest_uses_default_skill_location(self):
        manifest = self.load(".claude-plugin/plugin.json")
        self.assertEqual(manifest["name"], "requirements-impact-refiner")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertTrue(FORBIDDEN_COMPONENTS.isdisjoint(manifest))

    def test_manifest_identity_is_consistent(self):
        codex = self.load(".codex-plugin/plugin.json")
        claude = self.load(".claude-plugin/plugin.json")
        for key in ("name", "version", "description", "license"):
            self.assertEqual(codex[key], claude[key])


if __name__ == "__main__":
    unittest.main()
