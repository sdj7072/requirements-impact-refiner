import hashlib
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path, PurePosixPath

from evals.harness.catalog import CatalogError, load_all, load_catalog, select_suite
from evals.harness.models import CaseSpec, CaseTurn, RunRequest

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "cases.json"
CASE_SCHEMA_PATH = ROOT / "evals" / "harness" / "schemas" / "case.schema.json"
RESULT_SCHEMA_PATH = ROOT / "evals" / "harness" / "schemas" / "result.schema.json"
CASES_SHA256 = "a95817bfa5f75ea8d22eb80b3a41ab2c94195e619a9ad5e2ea9f00a8ae8b2628"


class EvalHarnessContractTest(unittest.TestCase):
    def test_installed_superpowers_suite_has_seventeen_cases(self):
        selected = select_suite(load_all(), "installed-superpowers")

        self.assertEqual(len(selected), 17)
        self.assertEqual(sum(case.kind == "positive" for case in selected), 8)
        self.assertEqual(sum(case.kind == "negative" for case in selected), 5)
        self.assertEqual(
            [case.id for case in selected if case.kind == "integration"],
            ["INT-superpowers"],
        )
        self.assertEqual(sum(case.kind == "lineage" for case in selected), 3)

    def test_smoke_suite_is_the_approved_gate(self):
        self.assertEqual(
            [case.id for case in select_suite(load_all(), "smoke")],
            [
                "POS-authorization",
                "NEG-debugging",
                "INT-superpowers",
                "LINEAGE-stable-blocked",
                "LINEAGE-reopened",
                "LINEAGE-no-false-resolution",
            ],
        )

    def test_installed_superpowers_rejects_mutated_required_composition(self):
        cases = load_all()
        integration = next(case for case in cases if case.id == "INT-superpowers")
        mutations = {
            "positive changed to negative": (
                cases[0],
                replace(cases[0], kind="negative"),
                "eight positive cases",
            ),
            "negative changed to lineage": (
                next(case for case in cases if case.kind == "negative"),
                replace(next(case for case in cases if case.kind == "negative"), kind="lineage"),
                "five negative cases",
            ),
            "integration identity replaced": (
                integration,
                replace(integration, id="INT-other", kind="positive"),
                "eight positive cases",
            ),
            "integration changed to lineage": (
                integration,
                replace(integration, kind="lineage"),
                "exactly INT-superpowers",
            ),
            "lineage changed to positive": (
                next(case for case in cases if case.kind == "lineage"),
                replace(next(case for case in cases if case.kind == "lineage"), kind="positive"),
                "eight positive cases",
            ),
        }

        for name, (original_case, mutated_case, message) in mutations.items():
            with self.subTest(name=name):
                mutated_cases = tuple(
                    mutated_case if case is original_case else case for case in cases
                )

                with self.assertRaisesRegex(CatalogError, message):
                    select_suite(mutated_cases, "installed-superpowers")

    def test_catalog_cases_are_immutable(self):
        case = CaseSpec(
            id="POS-example",
            kind="positive",
            turns=(CaseTurn("Change the editor role.", ("roles.py grants edit",)),),
            must_detect=("role boundary",),
            must_not_do=("write implementation plan",),
            modes=("codex",),
            fixture_files=(("src/roles.py", "def authorize_project_edit(): pass\n"),),
        )

        with self.assertRaises(FrozenInstanceError):
            case.id = "POS-mutated"

    def test_loader_rejects_invalid_contract_records(self):
        valid_case = {
            "id": "POS-example",
            "kind": "positive",
            "request": "Change the editor role.",
            "repository_evidence": ["roles.py grants edit"],
            "must_detect": ["role boundary"],
            "must_not_do": ["write implementation plan"],
            "modes": ["codex"],
            "fixture_files": [{"path": "src/roles.py", "content": "ROLE = 'editor'\n"}],
        }
        valid_lineage = {
            "id": "LINEAGE-example",
            "kind": "lineage",
            "turns": [
                {"prompt": "Record blocked state.", "repository_evidence": ["Report ID: RPT-1"]},
                {"prompt": "Keep the report blocked.", "repository_evidence": ["Report ID: RPT-1"]},
            ],
            "must_detect": ["stable RPT-1", "exact predecessor bytes"],
            "must_not_do": ["fabricate a decision"],
            "modes": ["superpowers"],
            "expected_transition": "unchanged",
            "fixture_files": [{"path": "src/export.py", "content": "def export(): pass\n"}],
        }
        invalid_records = {
            "duplicate IDs": ([valid_case, dict(valid_case)], [valid_lineage]),
            "unknown kind": ([dict(valid_case, kind="other")], [valid_lineage]),
            "unknown mode": ([dict(valid_case, modes=["other"])], [valid_lineage]),
            "blank prompt": ([dict(valid_case, request="   ")], [valid_lineage]),
            "non-list evidence": (
                [dict(valid_case, repository_evidence="roles.py")],
                [valid_lineage],
            ),
            "missing rubric": (
                [{key: value for key, value in valid_case.items() if key != "must_not_do"}],
                [valid_lineage],
            ),
            "duplicate rubric across fields": (
                [dict(valid_case, must_not_do=["role boundary"])],
                [valid_lineage],
            ),
            "incomplete lineage": (
                [valid_case],
                [dict(valid_lineage, turns=valid_lineage["turns"][:1])],
            ),
            "missing fixtures": (
                [{key: value for key, value in valid_case.items() if key != "fixture_files"}],
                [valid_lineage],
            ),
            "unsafe fixture path": (
                [dict(valid_case, fixture_files=[{"path": "../roles.py", "content": "x\n"}])],
                [valid_lineage],
            ),
            "reserved runtime fixture path": (
                [
                    dict(
                        valid_case,
                        fixture_files=[
                            {
                                "path": ".requirements-impact-refiner/reports/RPT-001/current.json",
                                "content": "{}\n",
                            }
                        ],
                    )
                ],
                [valid_lineage],
            ),
            "non-utf8 fixture path": (
                [dict(valid_case, fixture_files=[{"path": "src/\ud800.py", "content": "x\n"}])],
                [valid_lineage],
            ),
            "non-utf8 fixture content": (
                [dict(valid_case, fixture_files=[{"path": "src/roles.py", "content": "\ud800"}])],
                [valid_lineage],
            ),
            "duplicate fixture path": (
                [
                    dict(
                        valid_case,
                        fixture_files=[
                            {"path": "src/roles.py", "content": "x\n"},
                            {"path": "src/roles.py", "content": "y\n"},
                        ],
                    )
                ],
                [valid_lineage],
            ),
            "rubric leaked through fixture": (
                [
                    dict(
                        valid_case,
                        fixture_files=[{"path": "src/roles.py", "content": "role boundary\n"}],
                    )
                ],
                [valid_lineage],
            ),
        }

        for name, (cases, lineage) in invalid_records.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                base_path = root / "cases.json"
                lineage_path = root / "lineage.json"
                base_path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
                lineage_path.write_text(json.dumps({"cases": lineage}), encoding="utf-8")

                with self.assertRaises(CatalogError):
                    load_catalog(base_path, lineage_path)

    def test_canonical_cases_bytes_are_unchanged(self):
        self.assertEqual(hashlib.sha256(CASES_PATH.read_bytes()).hexdigest(), CASES_SHA256)

    def test_installed_cases_have_safe_nonleaking_fixture_contract(self):
        selected = select_suite(load_all(), "installed-superpowers")

        for case in selected:
            fixtures = case.fixture_files
            if case.kind in {"positive", "lineage"} or case.id == "INT-superpowers":
                self.assertTrue(fixtures, case.id)
            else:
                self.assertEqual(fixtures, (), case.id)
            fixture_text = "\n".join(path + "\n" + content for path, content in fixtures).casefold()
            for path, content in fixtures:
                pure = PurePosixPath(path)
                self.assertFalse(pure.is_absolute(), case.id)
                self.assertEqual(path, pure.as_posix(), case.id)
                self.assertNotIn("..", pure.parts, case.id)
                self.assertTrue(content.strip(), case.id)
            for rubric in (*case.must_detect, *case.must_not_do):
                self.assertNotIn(rubric.casefold(), fixture_text, case.id)

    def test_result_schema_exposes_every_public_artifact_type(self):
        schema = json.loads(RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            set(schema["$defs"]),
            {
                "adjudication",
                "clientProbe",
                "commandResult",
                "graphPerformanceObservation",
                "graphScore",
                "graphSmokeGateResult",
                "mechanicalScore",
                "performanceObservation",
                "runResult",
                "smokeGateResult",
            },
        )

    def test_retry_identity_is_typed_and_mirrored_in_the_result_schema(self):
        """Encoding attempts in repetition would make matrix keys non-integral."""
        fields = RunRequest.__dataclass_fields__
        schema = json.loads(RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
        run_result = schema["$defs"]["runResult"]

        self.assertEqual(fields["attempt"].default, 1)
        self.assertIsNone(fields["retry_of"].default)
        self.assertEqual(run_result["properties"]["attempt"], {"type": "integer", "minimum": 1})
        self.assertEqual(run_result["properties"]["retry_of"], {"type": ["string", "null"]})

    def test_case_schema_rejects_whitespace_for_every_loader_nonblank_string(self):
        schema = json.loads(CASE_SCHEMA_PATH.read_text(encoding="utf-8"))
        definitions = schema["$defs"]
        nonblank_schemas = (
            definitions["rubric"]["items"],
            definitions["turn"]["properties"]["prompt"],
            definitions["common"]["properties"]["id"],
            definitions["singleTurnCase"]["allOf"][1]["properties"]["id"],
            definitions["singleTurnCase"]["allOf"][1]["properties"]["request"],
            definitions["lineageCase"]["allOf"][1]["properties"]["id"],
            definitions["fixtureFile"]["properties"]["path"],
            definitions["fixtureFile"]["properties"]["content"],
        )

        self.assertTrue(all(item.get("pattern") == r"\S" for item in nonblank_schemas))
        self.assertIn("fixture_files", definitions["common"]["required"])


if __name__ == "__main__":
    unittest.main()
