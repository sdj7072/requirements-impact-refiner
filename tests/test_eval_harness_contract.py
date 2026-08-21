import hashlib
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from evals.harness.catalog import CatalogError, load_all, load_catalog, select_suite
from evals.harness.models import CaseSpec, CaseTurn


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "cases.json"
RESULT_SCHEMA_PATH = ROOT / "evals" / "harness" / "schemas" / "result.schema.json"
CASES_SHA256 = "03dbedb66900e89efec45fae7d73312fe2ccb6508a67e9143af3e3c88c1c53bc"


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

    def test_catalog_cases_are_immutable(self):
        case = CaseSpec(
            id="POS-example",
            kind="positive",
            turns=(CaseTurn("Change the editor role.", ("roles.py grants edit",)),),
            must_detect=("role boundary",),
            must_not_do=("write implementation plan",),
            modes=("codex",),
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
        }
        invalid_records = {
            "duplicate IDs": ([valid_case, dict(valid_case)], [valid_lineage]),
            "unknown kind": ([dict(valid_case, kind="other")], [valid_lineage]),
            "unknown mode": ([dict(valid_case, modes=["other"])], [valid_lineage]),
            "blank prompt": ([dict(valid_case, request="   ")], [valid_lineage]),
            "non-list evidence": ([dict(valid_case, repository_evidence="roles.py")], [valid_lineage]),
            "missing rubric": ([{key: value for key, value in valid_case.items() if key != "must_not_do"}], [valid_lineage]),
            "incomplete lineage": ([valid_case], [dict(valid_lineage, turns=valid_lineage["turns"][:1])]),
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

    def test_result_schema_exposes_every_public_artifact_type(self):
        schema = json.loads(RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            set(schema["$defs"]),
            {
                "adjudication",
                "clientProbe",
                "commandResult",
                "mechanicalScore",
                "runResult",
            },
        )


if __name__ == "__main__":
    unittest.main()
