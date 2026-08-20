import json
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_COMPONENTS = {"mcpServers", "apps", "hooks", "agents", "dependencies"}


class PackagingTest(unittest.TestCase):
    def load(self, relative_path):
        return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))

    def load_skill_identity(self):
        path = ROOT / "skills/requirements-impact-refiner/SKILL.md"
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(lines), 3)
        self.assertEqual(lines[0], "---")
        try:
            end = lines.index("---", 1)
        except ValueError:
            self.fail("canonical SKILL.md frontmatter is not closed")

        name = None
        version = None
        in_metadata = False
        for line in lines[1:end]:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            key, separator, raw_value = line.strip().partition(":")
            if not separator:
                continue
            if indent == 0:
                in_metadata = key == "metadata"
                if key == "name":
                    name = raw_value.strip().strip("\"'")
            elif in_metadata and key == "version":
                version = raw_value.strip().strip("\"'")

        self.assertTrue(name, "canonical SKILL.md frontmatter is missing name")
        self.assertTrue(
            version, "canonical SKILL.md frontmatter is missing metadata.version"
        )
        return name, version

    def test_canonical_skill_exists(self):
        self.assertTrue(
            (ROOT / "skills/requirements-impact-refiner/SKILL.md").is_file()
        )

    def test_codex_manifest_points_to_canonical_skills(self):
        manifest = self.load(".codex-plugin/plugin.json")
        self.assertEqual(manifest["name"], "requirements-impact-refiner")
        self.assertEqual(manifest["version"], "0.1.1")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertTrue(FORBIDDEN_COMPONENTS.isdisjoint(manifest))

    def test_claude_manifest_uses_default_skill_location(self):
        manifest = self.load(".claude-plugin/plugin.json")
        self.assertEqual(manifest["name"], "requirements-impact-refiner")
        self.assertEqual(manifest["version"], "0.1.1")
        self.assertTrue(FORBIDDEN_COMPONENTS.isdisjoint(manifest))

    def test_automatic_bootstrap_skill_is_discoverable(self):
        path = ROOT / "skills/using-requirements-impact-refiner/SKILL.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("name: using-requirements-impact-refiner", text)
        self.assertIn("Use when starting any software-development conversation", text)

    def test_automatic_entrypoint_owns_activation_boundaries(self):
        bootstrap = (
            ROOT / "skills/using-requirements-impact-refiner/SKILL.md"
        ).read_text(encoding="utf-8")
        core = (ROOT / "skills/requirements-impact-refiner/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("already impact-refined requirement or plan", bootstrap)
        self.assertNotIn("or approved plan", bootstrap)
        self.assertIn("bootstrap has selected", core)
        self.assertIn("with Superpowers, after approved brainstorming", core)
        self.assertIn("already impact-refined requirement or plan", core)

    def test_codex_manifest_references_a_readable_square_logo(self):
        manifest = self.load(".codex-plugin/plugin.json")
        interface = manifest["interface"]
        self.assertEqual(interface["composerIcon"], interface["logo"])
        logo_path = ROOT / interface["logo"]
        payload = logo_path.read_bytes()
        self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", payload[16:24])
        self.assertEqual(width, height)
        self.assertGreaterEqual(width, 512)

    def test_manifest_identity_is_consistent(self):
        codex = self.load(".codex-plugin/plugin.json")
        claude = self.load(".claude-plugin/plugin.json")
        for key in ("name", "version", "description", "license"):
            self.assertEqual(codex[key], claude[key])

    def test_manifests_match_canonical_skill_identity(self):
        skill_name, skill_version = self.load_skill_identity()
        for relative_path in (
            ".codex-plugin/plugin.json",
            ".claude-plugin/plugin.json",
        ):
            manifest = self.load(relative_path)
            self.assertEqual(manifest["name"], skill_name)
            self.assertEqual(manifest["version"], skill_version)


if __name__ == "__main__":
    unittest.main()
