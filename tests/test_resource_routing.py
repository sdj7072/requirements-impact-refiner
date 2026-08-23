import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "skills"
    / "requirements-impact-refiner"
    / "scripts"
    / "resource_route.py"
)
SPEC = importlib.util.spec_from_file_location("resource_route", MODULE_PATH)
ROUTING = importlib.util.module_from_spec(SPEC)
sys.modules["resource_route"] = ROUTING
SPEC.loader.exec_module(ROUTING)


class ResourceRoutingTest(unittest.TestCase):
    def test_cli_returns_the_exact_default_route(self):
        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--audience",
                "balanced",
                "--delivery",
                "compact",
                "--phase",
                "pre-decision",
                "--adapter",
                "generic",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "references": [
                    "references/compact-state-contract.md",
                    "references/integration-generic.md",
                ]
            },
        )

    def test_default_route_loads_only_compact_contract_and_selected_adapter(self):
        route = ROUTING.resolve_route(
            predecessor=False,
            evidence_ambiguity=False,
            multiple_domains=False,
            audience="balanced",
            delivery="compact",
            phase="pre-decision",
            adapter="generic",
        )

        self.assertEqual(
            route.references,
            (
                "references/compact-state-contract.md",
                "references/integration-generic.md",
            ),
        )

    def test_conditional_references_have_exact_observable_predicates(self):
        route = ROUTING.resolve_route(
            predecessor=True,
            evidence_ambiguity=True,
            multiple_domains=True,
            audience="technical",
            delivery="full",
            phase="post-decision",
            adapter="superpowers",
        )

        self.assertEqual(
            set(route.references),
            {
                "references/compact-state-contract.md",
                "references/integration-superpowers.md",
                "references/refinement-loop.md",
                "references/evidence-model.md",
                "references/impact-taxonomy.md",
                "references/presentation-modes.md",
                "assets/impact-report-post-decision-template.md",
            },
        )

    def test_each_condition_routes_only_its_own_reference(self):
        baseline = set(
            ROUTING.resolve_route(
                predecessor=False,
                evidence_ambiguity=False,
                multiple_domains=False,
                audience="balanced",
                delivery="compact",
                phase="pre-decision",
                adapter="generic",
            ).references
        )
        cases = (
            ("predecessor", {"predecessor": True}, "references/refinement-loop.md"),
            ("evidence", {"evidence_ambiguity": True}, "references/evidence-model.md"),
            ("domains", {"multiple_domains": True}, "references/impact-taxonomy.md"),
            ("audience", {"audience": "simple"}, "references/presentation-modes.md"),
            ("full", {"delivery": "full"}, "assets/impact-report-pre-decision-template.md"),
        )
        defaults = {
            "predecessor": False,
            "evidence_ambiguity": False,
            "multiple_domains": False,
            "audience": "balanced",
            "delivery": "compact",
            "phase": "pre-decision",
            "adapter": "generic",
        }
        for name, override, expected in cases:
            with self.subTest(name=name):
                route = ROUTING.resolve_route(**{**defaults, **override})
                self.assertEqual(set(route.references) - baseline, {expected})

    def test_unknown_route_values_are_rejected(self):
        defaults = {
            "predecessor": False,
            "evidence_ambiguity": False,
            "multiple_domains": False,
            "audience": "balanced",
            "delivery": "compact",
            "phase": "pre-decision",
            "adapter": "generic",
        }
        for field, value in (
            ("audience", "friendly"),
            ("delivery", "short"),
            ("phase", "planning"),
            ("adapter", "combined"),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    ROUTING.resolve_route(**{**defaults, field: value})


if __name__ == "__main__":
    unittest.main()
