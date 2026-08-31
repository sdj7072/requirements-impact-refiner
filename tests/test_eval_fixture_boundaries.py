import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from evals.harness.adapters.codex import CodexAdapter
from evals.harness.catalog import load_all, select_suite

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


FAST_SCAN = load_module("eval_fixture_fast_scan", SCRIPTS / "fast_scan.py")


class OpenDeadline:
    def expired(self):
        return False


class EvaluationFixtureBoundaryTest(unittest.TestCase):
    def test_every_nonnegative_smoke_case_has_a_repository_backed_first_turn_seed(self):
        for case in select_suite(load_all(), "smoke"):
            if case.kind == "negative":
                continue
            with self.subTest(case=case.id), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                CodexAdapter._stage_catalog_fixture(case, root)
                turn = case.turns[0]

                seeds = FAST_SCAN.derive_seeds(
                    root,
                    turn.prompt,
                    turn.repository_evidence,
                    OpenDeadline(),
                )

                self.assertTrue(seeds, case.id)
                self.assertTrue(
                    any(seed.location in dict(case.fixture_files) for seed in seeds),
                    case.id,
                )

    def test_reopened_lineage_exposes_desktop_evidence_only_after_followup_staging(self):
        case = next(case for case in load_all() if case.id == "LINEAGE-reopened")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            CodexAdapter._stage_catalog_fixture(case, root)
            second_turn = case.turns[1]

            before = FAST_SCAN.derive_seeds(
                root,
                second_turn.prompt,
                second_turn.repository_evidence,
                OpenDeadline(),
            )
            CodexAdapter._stage_followup_fixture(case, root)
            after = FAST_SCAN.derive_seeds(
                root,
                second_turn.prompt,
                second_turn.repository_evidence,
                OpenDeadline(),
            )

            self.assertNotIn("desktop/ProfileCache.swift", {seed.location for seed in before})
            self.assertIn("desktop/ProfileCache.swift", {seed.location for seed in after})


if __name__ == "__main__":
    unittest.main()
