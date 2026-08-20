import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READMES = ["README.md", "README.ko.md", "README.ja.md"]
LANGUAGE_TARGETS = {"README.md", "README.ko.md", "README.ja.md"}


def headings(path):
    text = path.read_text(encoding="utf-8")
    return [
        re.sub(r"^#+\s+", "", line).strip()
        for line in text.splitlines()
        if line.startswith("## ")
    ]


class DocumentationTest(unittest.TestCase):
    def test_all_languages_exist_and_link_to_each_other(self):
        for name in READMES:
            path = ROOT / name
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            linked = set(re.findall(r"README(?:\.ko|\.ja)?\.md", text))
            self.assertEqual(linked, LANGUAGE_TARGETS)

    def test_all_languages_have_ten_numbered_sections(self):
        for name in READMES:
            numbered = [h for h in headings(ROOT / name) if re.match(r"\d+\.", h)]
            self.assertEqual(len(numbered), 10, name)

    def test_compatibility_terms_exist_in_every_language(self):
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for term in ("Codex", "Claude Code", "Superpowers", "Spec Kit"):
                self.assertIn(term, text, f"{term} missing from {name}")

    def test_license_and_contributing_exist(self):
        self.assertIn("MIT License", (ROOT / "LICENSE").read_text(encoding="utf-8"))
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("README.ko.md", contributing)
        self.assertIn("README.ja.md", contributing)


if __name__ == "__main__":
    unittest.main()
