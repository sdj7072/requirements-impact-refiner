import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RENDERER = load_module("impact_renderer", SKILL_SCRIPTS / "impact_renderer.py")
DOMAIN = load_module("impact_report", SKILL_SCRIPTS / "impact_report.py")
CONTROLLER = load_module("rir_controller", SKILL_SCRIPTS / "rir_controller.py")
CLI = SKILL_SCRIPTS / "render-impact-report.py"


def semantic_tables(text):
    parsed, errors = DOMAIN.parse_report(text)
    if errors:
        raise AssertionError(errors)
    return parsed.tables


class ImpactRendererTest(unittest.TestCase):
    def fixture(self, name="compact-state-post-decision.json"):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def controller_graph_state(self, audience="technical", count=2):
        analysis = json.loads(
            (FIXTURES / "controller-analysis-pre-decision.json").read_text(
                encoding="utf-8"
            )
        )
        providers = ("codegraph", "scip")
        nodes, edges, paths = [], [], []
        for index in range(count):
            path_id = f"PATH-{index + 1:03d}"
            provider = providers[index % len(providers)]
            start, end, edge = (
                f"NODE-{index * 2 + 1:03d}",
                f"NODE-{index * 2 + 2:03d}",
                f"EDGE-{index + 1:03d}",
            )
            label = f"<api-{index} data-x='1' || `wire|field`> " + "very-long-label " * 40
            nodes.extend((
                {"id": start, "label": label, "provider": provider, "confidence": "verified-provider", "location": f"api/profile_{index}.py"},
                {"id": end, "label": f"desktop cache {index}", "provider": provider, "confidence": "verified-provider", "location": f"desktop/cache_{index}.ts"},
            ))
            edges.append({"id": edge, "provider": provider, "confidence": "verified-provider", "location": f"desktop/cache_{index}.ts"})
            paths.append({"id": path_id, "nodes": [start, end], "edges": [edge]})
        key = analysis["impacts"][0]["key"]
        analysis["impacts"][0]["graph_path_keys"] = [row["id"] for row in paths]
        settings = {
            "audience": audience, "audience_source": "request",
            "delivery": "compact", "delivery_source": "default",
            "impact_graph": {"enabled": True, "max_seconds": 30, "target_seconds": 10, "providers": ["auto"], "install_policy": "never", "deep": False},
        }
        state, _ = CONTROLLER._build_state(
            {"request": "Change profile", "settings": settings, "adapter": "generic", "prior_state": None, "prior_key_map": {}, "report_id": "RPT-001", "revision": 1, "previous_sha256": "none"},
            analysis,
            {
                "receipt": {
                    "nodes": nodes, "edges": edges, "paths": paths,
                    "providers": [{"name": name, "status": "ready"} for name in providers],
                    "timings_ms": {"total": 8400}, "frontier": [{"id": "FRONTIER-001"}, {"id": "FRONTIER-002"}],
                    "budget_status": "provider_limited", "receipt_id": "a" * 32,
                },
                "impact_paths": {key: [row["id"] for row in paths]},
                "rationales": {key: None},
                "impact_confidences": {key: "verified-provider"},
                "sha256": "a" * 64,
            },
        )
        return state

    def test_markdown_render_is_byte_deterministic_and_validator_clean(self):
        state = self.fixture()

        first = RENDERER.render_markdown(state)
        second = RENDERER.render_markdown(state)

        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))
        self.assertEqual(
            first,
            (FIXTURES / "compact-state-post-decision.md").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(RENDERER.validate_rendered_markdown(first), [])

    def test_compact_render_names_every_impact_once_and_stays_bounded(self):
        state = self.fixture()

        rendered = RENDERER.render_compact(state)

        for impact in state["impacts"]:
            self.assertEqual(rendered.count(impact["id"]), 1)
        self.assertLessEqual(len(rendered.split()), 450)
        self.assertIn("Full report:", rendered)
        self.assertIn("Validation: passed", rendered)

    def test_compact_output_uses_controller_receipt_paths_and_unknown_frontier(self):
        state = self.controller_graph_state()

        text = RENDERER.render_compact(state)

        self.assertIn("&lt;api-0 data-x='1' &#124;&#124; &#96;wire&#124;field&#96;&gt;", text)
        self.assertIn("Impact scan: 8.4 s", text)
        self.assertIn("2 unknown frontiers", text)
        self.assertEqual(text.count("Impact scan:"), 1)

    def test_compact_graph_details_follow_audience_and_exact_controller_provenance(self):
        simple = RENDERER.render_compact(self.controller_graph_state("simple"))
        balanced = RENDERER.render_compact(self.controller_graph_state("balanced"))
        technical_state = self.controller_graph_state("technical")
        technical = RENDERER.render_compact(technical_state)

        self.assertIn("&lt;api-0 data-x='1' &#124;&#124; &#96;wire&#124;field&#96;&gt;", simple)
        self.assertNotIn("PATH-001", simple)
        self.assertIn("PATH-001: &lt;api-0 data-x='1' &#124;&#124; &#96;wire&#124;field&#96;&gt;", balanced)
        self.assertIn("PATH-001: &lt;api-0 data-x='1' &#124;&#124; &#96;wire&#124;field&#96;&gt;", technical)
        self.assertIn("provider codegraph; confidence verified-provider; location api/profile_0.py", technical)
        structured = technical_state["graph_paths"][0]["paths"]
        self.assertEqual(structured[1]["providers"], ["scip"])
        self.assertEqual(structured[1]["locations"][0], "api/profile_1.py")
        self.assertEqual(CONTROLLER.compact_state.validate_state(technical_state), [])
        self.assertNotIn("provider codegraph + scip", technical)

    def test_compact_graph_output_stays_bounded_without_malformed_markdown(self):
        for audience in ("simple", "balanced", "technical"):
            rendered = RENDERER.render_compact(
                self.controller_graph_state(audience, count=32)
            )
            self.assertLessEqual(len(rendered.split()), 450, audience)
            self.assertIn("Impact scan: 8.4 s", rendered)
            self.assertIn("2 unknown frontiers", rendered)
            self.assertIn("`IMP-001`", rendered)
            self.assertFalse(any("<api-" in line for line in rendered.splitlines()))
            for line in rendered.splitlines():
                if line.startswith("|"):
                    self.assertEqual(line.count("|"), 5)

    def test_existing_markdown_converts_without_semantic_loss(self):
        markdown = (FIXTURES / "compact-state-post-decision.md").read_text(
            encoding="utf-8"
        )

        state, errors = RENDERER.state_from_markdown(markdown)

        self.assertEqual(errors, [])
        self.assertEqual(
            semantic_tables(RENDERER.render_markdown(state)),
            semantic_tables(markdown),
        )

    def test_cell_escaping_preserves_table_shape_and_non_ascii(self):
        state = self.fixture()
        state["summary"][0]["possible_issue"] = "<img src=x> 한글 | 日本語\n`code`"

        rendered = RENDERER.render_markdown(state)
        parsed, errors = RENDERER.state_from_markdown(rendered)

        self.assertEqual(errors, [])
        self.assertEqual(
            parsed["summary"][0]["possible_issue"], "<img src=x> 한글 | 日本語\n`code`"
        )
        self.assertIn("&lt;img src=x&gt;", rendered)

    def test_cli_refuses_overwrite_without_force_and_supports_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            report_path = root / "report.md"
            roundtrip_path = root / "roundtrip.json"
            state_path.write_text(
                json.dumps(self.fixture(), ensure_ascii=False), encoding="utf-8"
            )

            first = subprocess.run(
                [sys.executable, str(CLI), str(state_path), "--format", "markdown", "--output", str(report_path)],
                text=True, capture_output=True, check=False,
            )
            second = subprocess.run(
                [sys.executable, str(CLI), str(state_path), "--format", "markdown", "--output", str(report_path)],
                text=True, capture_output=True, check=False,
            )
            converted = subprocess.run(
                [sys.executable, str(CLI), "--from-markdown", str(report_path), "--output", str(roundtrip_path)],
                text=True, capture_output=True, check=False,
            )

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 2)
            self.assertIn("output already exists", second.stderr)
            self.assertEqual(converted.returncode, 0, converted.stderr)
            self.assertEqual(json.loads(roundtrip_path.read_text()), self.fixture())


if __name__ == "__main__":
    unittest.main()
