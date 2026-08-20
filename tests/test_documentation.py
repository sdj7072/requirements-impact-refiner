import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READMES = ["README.md", "README.ko.md", "README.ja.md"]
LANGUAGE_TARGETS = {"README.md", "README.ko.md", "README.ja.md"}
SKILL_ROOT = ROOT / "skills" / "requirements-impact-refiner"


def headings(path):
    text = path.read_text(encoding="utf-8")
    return [
        re.sub(r"^#+\s+", "", line).strip()
        for line in text.splitlines()
        if line.startswith("## ")
    ]


def compatibility_identity_rows(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if re.match(r"^## 6\.", line)
    )
    header = next(
        index
        for index in range(start + 1, len(lines))
        if lines[index].startswith("| Environment | Version | Status |")
    )
    rows = []
    for line in lines[header + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append(tuple(cells[:3]))
    return rows


class DocumentationTest(unittest.TestCase):
    def test_future_acceptance_criterion_examples_are_not_verified_findings(self):
        for path in (SKILL_ROOT / "references").glob("*.md"):
            header = None
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.startswith("|"):
                    header = None
                    continue
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if "ID" in cells and "Level" in cells:
                    header = cells
                    continue
                if header and re.fullmatch(r"`?AC-\d{3}`?", cells[0]):
                    level = cells[header.index("Level")].strip("`").lower()
                    self.assertNotEqual(
                        level,
                        "verified",
                        f"future target is labelled as current proof in {path}",
                    )

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

    def test_compatibility_identity_and_status_rows_match_in_every_language(self):
        canonical = compatibility_identity_rows(ROOT / "README.md")
        self.assertEqual(len(canonical), 9)
        for name in READMES[1:]:
            self.assertEqual(
                compatibility_identity_rows(ROOT / name),
                canonical,
                name,
            )

    def test_license_and_contributing_exist(self):
        self.assertIn("MIT License", (ROOT / "LICENSE").read_text(encoding="utf-8"))
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("README.ko.md", contributing)
        self.assertIn("README.ja.md", contributing)


if __name__ == "__main__":
    unittest.main()
