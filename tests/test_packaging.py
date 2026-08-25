import importlib.util
import json
import re
import shlex
import shutil
import struct
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_COMPONENTS = {"mcpServers", "apps", "hooks", "agents", "dependencies"}
PAYLOAD_SPEC = importlib.util.spec_from_file_location(
    "payload_identity_test", ROOT / "scripts" / "payload_identity.py"
)
PAYLOAD_IDENTITY = importlib.util.module_from_spec(PAYLOAD_SPEC)
PAYLOAD_SPEC.loader.exec_module(PAYLOAD_IDENTITY)


def ci_run_commands(workflow_text):
    """Extract executable shell content from GitHub Actions ``run`` steps."""
    lines = workflow_text.splitlines()
    commands = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(?P<indent>\s*)(?:-\s+)?run:\s*(?P<content>.*)$", lines[index])
        if match is None:
            index += 1
            continue
        content = match.group("content").strip()
        if content not in {"|", ">", "|-", ">-"}:
            commands.append(content)
            index += 1
            continue
        indentation = len(match.group("indent"))
        index += 1
        block = []
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= indentation:
                break
            block.append(line[indentation + 2 :] if len(line) > indentation + 2 else "")
            index += 1
        commands.extend(line for line in block if line.strip())
    return tuple(commands)


def unsafe_ci_commands(workflow_text):
    """Return run steps currently rejected by the CI safety contract."""
    unsafe = []
    for command in ci_run_commands(workflow_text):
        if any(unsafe_ci_argv(argv) for argv in shell_argvs(command)):
            unsafe.append(command)
    return tuple(unsafe)


def shell_argvs(command):
    """Split a shell line into argv-like commands without executing it."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    commands = []
    argv = []
    for token in lexer:
        if token in {"|", "||", "&", "&&", ";"}:
            if argv:
                commands.append(tuple(argv))
                argv = []
        else:
            argv.append(token)
    if argv:
        commands.append(tuple(argv))
    return tuple(commands)


def unsafe_ci_argv(argv):
    """Classify argv-like live-client mutation, authentication, or model calls."""
    while argv and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", argv[0]):
        argv = argv[1:]
    if not argv:
        return False

    command, *arguments = argv
    if Path(command).name == "env":
        for index, argument in enumerate(arguments):
            if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", Path(argument).name):
                command, arguments = argument, arguments[index + 1 :]
                break
    python_name = Path(command).name
    if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", python_name):
        if any(
            argument == "-m" and arguments[index + 1] == "evals.harness.run"
            for index, argument in enumerate(arguments[:-1])
        ):
            return True
    if command == "codex" and arguments[:1] == ["exec"]:
        return True
    if command == "codex" and arguments[:3] == ["plugin", "marketplace", "upgrade"]:
        return True
    if command == "codex" and tuple(arguments[:2]) in {
        ("plugin", "add"),
        ("plugin", "remove"),
    }:
        return True
    if any("claude.ai/install.sh" in argument for argument in argv):
        return True
    if command == "brew" and {"install", "--cask", "claude-code"}.issubset(arguments):
        return True
    if (
        command == "npm"
        and arguments
        and arguments[0] in {"install", "i"}
        and {"-g", "--global"}.intersection(arguments)
        and "claude-code" in arguments
    ):
        return True
    if command == "/login":
        return True
    if command != "claude":
        return False
    if not arguments or arguments[0] in {"auth", "login", "logout", "setup-token"}:
        return True
    return "-p" in arguments or "--print" in arguments


def assert_safe_ci_workflow(workflow_text):
    unsafe = unsafe_ci_commands(workflow_text)
    if unsafe:
        raise AssertionError(f"unsafe CI run command(s): {unsafe!r}")


def checkout_step_inputs(workflow_text):
    """Parse the checkout step's explicit inputs without executing CI commands."""
    lines = workflow_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "- uses: actions/checkout@v4":
            continue
        inputs = {}
        in_with_block = False
        for nested in lines[index + 1 :]:
            if nested.startswith("      - "):
                break
            if nested.strip() == "with:":
                in_with_block = True
                continue
            match = re.match(r"^\s{10}(?P<key>[\w-]+):\s*(?P<value>\S+)\s*$", nested)
            if in_with_block and match:
                inputs[match.group("key")] = match.group("value")
        return inputs
    raise AssertionError("CI workflow is missing actions/checkout@v4")


class PackagingTest(unittest.TestCase):
    def test_payload_identity_covers_every_live_mcp_dependency_and_mutation(self):
        required = {
            ".codex-plugin/plugin.json",
            ".mcp.json",
            "schemas/controller-analysis.schema.json",
            "schemas/compact-state.schema.json",
            "schemas/impact-graph-receipt.schema.json",
            "schemas/fast-impact-scan.schema.json",
            "scripts/launch-rir-mcp",
            "scripts/payload_identity.py",
            "scripts/rir-controller.py",
            "scripts/rir_mcp_server.py",
            "scripts/rir_controller.py",
            "scripts/rir_contracts.py",
            "scripts/rir_finalize.py",
            "scripts/rir_lineage.py",
            "scripts/rir_storage.py",
            "scripts/compact_state.py",
            "scripts/impact_graph.py",
            "scripts/graph_builtin.py",
            "scripts/fast_scan.py",
            "scripts/graph_cache.py",
            "scripts/rir_graph_delivery.py",
            "scripts/graph_providers.py",
            "scripts/graph_coordinator.py",
            "scripts/graph_adapter_ast_grep.py",
            "scripts/graph_adapter_codegraph.py",
            "scripts/graph_adapter_scip.py",
            "scripts/graph_adapter_joern.py",
            "scripts/impact_renderer.py",
            "scripts/impact_report.py",
            "scripts/validate-impact-report.py",
            "scripts/report_store.py",
            "scripts/resolve-settings.py",
        }
        paths = PAYLOAD_IDENTITY.functional_paths(ROOT)
        relative = {path.relative_to(ROOT).as_posix() for path in paths}
        self.assertTrue(required <= relative)
        with tempfile.TemporaryDirectory() as temporary:
            copy_root = Path(temporary) / "plugin"
            for source in paths:
                destination = copy_root / source.relative_to(ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            baseline = PAYLOAD_IDENTITY.payload_sha256(copy_root)
            for name in sorted(required):
                target = copy_root / name
                original = target.read_bytes()
                target.write_bytes(original + b"\nmutation")
                self.assertNotEqual(PAYLOAD_IDENTITY.payload_sha256(copy_root), baseline, name)
                target.write_bytes(original)

    def test_runtime_lock_artifacts_are_neither_tracked_nor_shipped(self):
        tracked_result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        tracked = tuple(path.decode("utf-8") for path in tracked_result.stdout.split(b"\0") if path)

        def is_runtime_lock(path):
            return path == ".requirements-impact-refiner/drafts/.draft-transaction.lock" or (
                re.fullmatch(
                    r"\.requirements-impact-refiner/reports/[^/]+/\.controller\.lock",
                    path,
                )
                is not None
            )

        self.assertEqual(tuple(path for path in tracked if is_runtime_lock(path)), ())
        shipped = tuple(
            path.relative_to(ROOT).as_posix() for path in PAYLOAD_IDENTITY.functional_paths(ROOT)
        )
        self.assertEqual(tuple(path for path in shipped if is_runtime_lock(path)), ())

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
        self.assertTrue(version, "canonical SKILL.md frontmatter is missing metadata.version")
        return name, version

    def test_canonical_skill_exists(self):
        self.assertTrue((ROOT / "skills/requirements-impact-refiner/SKILL.md").is_file())

    def test_codex_manifest_points_to_canonical_skills(self):
        manifest = self.load(".codex-plugin/plugin.json")
        self.assertEqual(manifest["name"], "requirements-impact-refiner")
        self.assertEqual(manifest["version"], "0.5.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        self.assertTrue((FORBIDDEN_COMPONENTS - {"mcpServers"}).isdisjoint(manifest))

    def test_claude_manifest_uses_default_skill_location(self):
        manifest = self.load(".claude-plugin/plugin.json")
        self.assertEqual(manifest["name"], "requirements-impact-refiner")
        self.assertEqual(manifest["version"], "0.5.0")
        self.assertTrue(FORBIDDEN_COMPONENTS.isdisjoint(manifest))

    def test_mcp_config_uses_local_relative_launcher_without_credentials(self):
        config = self.load(".mcp.json")
        self.assertEqual(set(config), {"mcpServers"})
        self.assertEqual(set(config["mcpServers"]), {"requirements-impact-refiner"})
        server = config["mcpServers"]["requirements-impact-refiner"]
        self.assertEqual(server["command"], "./scripts/launch-rir-mcp")
        self.assertEqual(server["args"], [])
        self.assertEqual(server["cwd"], ".")
        self.assertNotIn("url", server)
        self.assertEqual(server.get("env_vars", []), [])
        launcher = ROOT / "scripts/launch-rir-mcp"
        self.assertTrue(launcher.is_file())
        self.assertTrue(launcher.stat().st_mode & 0o111)

    def test_automatic_bootstrap_skill_is_discoverable(self):
        path = ROOT / "skills/using-requirements-impact-refiner/SKILL.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("name: using-requirements-impact-refiner", text)
        self.assertIn("Use when starting any software-development conversation", text)
        self.assertIn('version: "0.5.0"', text)

    def test_compact_delivery_demo_svg_is_safe_and_accessible(self):
        path = ROOT / "assets/compact-delivery-demo.svg"
        self.assertTrue(path.is_file())
        tree = ET.parse(path)
        root = tree.getroot()
        self.assertEqual(root.attrib.get("viewBox"), "0 0 1200 600")
        titles = [element.text for element in root.iter() if element.tag.endswith("title")]
        self.assertTrue(any(title and title.strip() for title in titles))
        self.assertFalse(any(element.tag.endswith("script") for element in root.iter()))
        for element in root.iter():
            for key, value in element.attrib.items():
                if key.endswith("href"):
                    self.assertFalse(value.startswith(("http://", "https://", "//")))

    def test_automatic_entrypoint_owns_activation_boundaries(self):
        bootstrap = (ROOT / "skills/using-requirements-impact-refiner/SKILL.md").read_text(
            encoding="utf-8"
        )
        core = (ROOT / "skills/requirements-impact-refiner/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("already impact-refined requirement or plan", bootstrap)
        self.assertNotIn("or approved plan", bootstrap)
        self.assertIn("bootstrap has selected", core)
        self.assertIn("with Superpowers, after approved brainstorming", core)
        self.assertIn("already impact-refined requirement or plan", core)

    def test_stage_templates_are_disjoint_and_complete(self):
        assets = ROOT / "skills/requirements-impact-refiner/assets"
        chooser = (assets / "impact-report-template.md").read_text(encoding="utf-8")
        pre = (assets / "impact-report-pre-decision-template.md").read_text(encoding="utf-8")
        post = (assets / "impact-report-post-decision-template.md").read_text(encoding="utf-8")

        self.assertIn("impact-report-pre-decision-template.md", chooser)
        self.assertIn("impact-report-post-decision-template.md", chooser)
        self.assertIn("--previous", chooser)
        self.assertIn("--print-expected-delta", chooser)
        self.assertIn("| pre-decision |", pre)
        self.assertIn("## Decision Needed", pre)
        self.assertNotIn("DEC-###", pre)
        self.assertNotIn("## Decisions and Accepted Risks", pre)
        self.assertIn("| post-decision |", post)
        self.assertIn("## Decisions and Accepted Risks", post)
        self.assertNotIn("## Decision Needed", post)
        for text in (pre, post):
            self.assertIn("| Report ID | Revision | Previous SHA-256 | Phase |", text)
            self.assertIn("## Impact Delta", text)
            self.assertIn("## Change Impact Summary", text)
            self.assertIn("List only ledger impacts whose state is `deferred` or `blocked`", text)
            for category in (
                "resolved",
                "mitigated",
                "unchanged",
                "accepted",
                "deferred",
                "blocked",
                "superseded",
                "reopened",
                "new",
            ):
                self.assertIn(f"| {category} |", text)

    def test_distribution_contains_reusable_report_domain_module(self):
        scripts = ROOT / "skills/requirements-impact-refiner/scripts"

        self.assertTrue((scripts / "impact_report.py").is_file())

    def test_distribution_contains_graph_receipt_contract(self):
        canonical = ROOT / "skills" / "requirements-impact-refiner"
        self.assertTrue((canonical / "scripts" / "impact_graph.py").is_file())
        self.assertTrue((canonical / "schemas" / "impact-graph-receipt.schema.json").is_file())

    def test_distribution_contains_fast_scan_contract(self):
        canonical = ROOT / "skills" / "requirements-impact-refiner"
        script = canonical / "scripts" / "fast_scan.py"
        schema = canonical / "schemas" / "fast-impact-scan.schema.json"
        self.assertTrue(script.is_file())
        self.assertTrue(schema.is_file())
        self.assertEqual(script.read_bytes(), (ROOT / "scripts/fast_scan.py").read_bytes())
        self.assertEqual(
            schema.read_bytes(),
            (ROOT / "schemas/fast-impact-scan.schema.json").read_bytes(),
        )

    def test_distribution_contains_graph_scanner_and_cache(self):
        canonical = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
        self.assertTrue((canonical / "graph_builtin.py").is_file())
        self.assertTrue((canonical / "graph_cache.py").is_file())

    def test_distribution_contains_provider_runner_and_coordinator(self):
        canonical = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
        self.assertTrue((canonical / "graph_providers.py").is_file())
        self.assertTrue((canonical / "graph_coordinator.py").is_file())

    def test_distribution_contains_all_detect_only_graph_adapters(self):
        canonical = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
        for name in ("ast_grep", "codegraph", "scip", "joern"):
            self.assertTrue((canonical / (f"graph_adapter_{name}.py")).is_file())

    def test_plugin_root_resource_fallback_mirrors_are_complete_and_identical(self):
        """Plugin-root fallbacks must exactly preserve canonical skill resources."""
        canonical = ROOT / "skills" / "requirements-impact-refiner"
        mirror_contract = {
            "references": set(),
            "assets": {Path("logo.png"), Path("compact-delivery-demo.svg")},
            "scripts": {
                Path("install-agent-skill.py"),
                Path("launch-rir-mcp"),
                Path("rir_mcp_server.py"),
                Path("run-quality-gates.py"),
            },
            "schemas": set(),
        }

        for directory, root_only_files in mirror_contract.items():
            canonical_dir = canonical / directory
            canonical_files = {
                path.relative_to(canonical_dir)
                for path in canonical_dir.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            }
            mirror_dir = ROOT / directory
            mirror_files = {
                path.relative_to(mirror_dir)
                for path in mirror_dir.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            }

            self.assertEqual(mirror_files, canonical_files | root_only_files)
            for relative_path in canonical_files:
                self.assertEqual(
                    (mirror_dir / relative_path).read_bytes(),
                    (canonical_dir / relative_path).read_bytes(),
                    f"{directory}/{relative_path} must be byte-identical to canonical",
                )

        self.assertFalse((ROOT / "SKILL.md").exists())
        self.assertFalse((canonical / "scripts" / "run-quality-gates.py").exists())

    def test_codex_manifest_references_a_standard_root_logo(self):
        manifest = self.load(".codex-plugin/plugin.json")
        interface = manifest["interface"]
        self.assertEqual(interface["composerIcon"], "./assets/logo.png")
        self.assertEqual(interface["logo"], "./assets/logo.png")
        self.assertEqual(interface["composerIcon"], interface["logo"])
        logo_path = ROOT / interface["logo"]
        payload = logo_path.read_bytes()
        self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", payload[16:24])
        self.assertEqual(width, height)
        self.assertGreaterEqual(width, 512)
        self.assertLess(len(payload), 1_300_000)
        self.assertIn(payload[25], (4, 6), "logo PNG must include an alpha channel")
        self.assertEqual(
            payload,
            (ROOT / ".codex-plugin/assets/logo.png").read_bytes(),
            "the root-standard logo must preserve the established artwork",
        )

    def test_core_skill_resolves_resources_from_its_own_directory(self):
        core = (ROOT / "skills/requirements-impact-refiner/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Resolve links from this `SKILL.md` directory", core)
        self.assertIn("references/fast-scan.md", core)
        self.assertIn("references/controller-workflow.md", core)
        self.assertNotIn("references/transitive-impact-graph.md", core)
        self.assertIn("exactly one adapter", core)

    def test_core_skill_defaults_to_compact_with_full_inline_fallback(self):
        core = (ROOT / "skills/requirements-impact-refiner/SKILL.md").read_text(encoding="utf-8")
        workflow = (
            ROOT / "skills/requirements-impact-refiner/references/controller-workflow.md"
        ).read_text(encoding="utf-8")
        self.assertIn("`balanced` + `compact`", workflow)
        self.assertIn("scripts/rir-controller.py", core)
        self.assertIn("renderer-owned display text", workflow)
        self.assertIn("full-inline", core)
        self.assertIn("Every affected behavior gets an impact row", workflow)

    def test_distribution_contains_transitive_impact_graph_reference_mirror(self):
        canonical = (
            ROOT / "skills/requirements-impact-refiner/references/transitive-impact-graph.md"
        )
        mirror = ROOT / "references/transitive-impact-graph.md"
        self.assertTrue(canonical.is_file())
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())

    def test_core_skill_runs_routing_before_workspace_availability_checks(self):
        core = (ROOT / "skills/requirements-impact-refiner/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`rir_scan`", core)
        self.assertIn("supplied evidence", core.lower())
        self.assertIn(
            "Stop; the renderer-owned question already asks whether to refine",
            core,
        )

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

    def test_ci_exercises_and_compiles_the_harness_without_live_clients(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("python3 -m unittest discover -s tests -v", workflow)
        self.assertIn("python3 -m compileall -q evals/harness", workflow)
        self.assertEqual(unsafe_ci_commands(workflow), ())

    def test_ci_checkout_fetches_the_pinned_payload_commit(self):
        """A shallow checkout cannot verify the sealed d92 payload basis in CI."""
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertEqual(checkout_step_inputs(workflow), {"fetch-depth": "0"})

    def test_ci_safety_rejects_live_client_mutations_in_run_steps(self):
        """Adding a live mutation/auth/model command must break CI safety."""
        unsafe_steps = (
            "codex exec 'evaluate this'",
            "codex plugin marketplace upgrade requirements-impact-refiner",
            "codex plugin add requirements-impact-refiner@requirements-impact-refiner",
            "codex plugin remove requirements-impact-refiner@requirements-impact-refiner",
            "curl -fsSL https://claude.ai/install.sh | bash",
            "brew install --cask claude-code",
            "npm install --global claude-code",
            "claude auth login",
            "claude auth logout",
            "claude auth setup-token",
            "/login",
            "claude -p 'evaluate this'",
            "claude --print 'evaluate this'",
            "claude",
            "python -m evals.harness.run --client codex --probe-only --output out",
            "python3 -m evals.harness.run --client codex --suite smoke --output out",
            "python3.11 -m evals.harness.run --client claude --probe-only --output out",
            "/usr/bin/python3 -m evals.harness.run --client codex --suite installed-superpowers --output out",
            "PYTHONPYCACHEPREFIX=/tmp/ci python3 -m evals.harness.run --client codex --probe-only --output out",
            "env python3 -m evals.harness.run --client codex --probe-only --output out",
            "/usr/bin/env python3 -m evals.harness.run --client claude --probe-only --output out",
            "/usr/bin/env FOO=bar python3 -m evals.harness.run --client codex --suite smoke --output out",
            "env -i python3 -m evals.harness.run --client codex --suite smoke --output out",
        )
        for command in unsafe_steps:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as temporary:
                workflow_path = Path(temporary) / "ci.yml"
                workflow_path.write_text(
                    f"jobs:\n  test:\n    steps:\n      - run: |\n          {command}\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(AssertionError, "unsafe CI run command"):
                    assert_safe_ci_workflow(workflow_path.read_text(encoding="utf-8"))

    def test_ci_safety_ignores_non_executable_claude_mentions(self):
        self.assertEqual(
            unsafe_ci_commands("Documentation may discuss `claude auth` outside a CI run step.\n"),
            (),
        )
        self.assertEqual(
            unsafe_ci_commands(
                "jobs:\n  test:\n    steps:\n"
                "      - run: python3 -m py_compile evals/harness/adapters/claude.py\n"
            ),
            (),
        )

    def test_ci_safety_allows_python_test_and_compile_modules(self):
        """The live harness ban must not disable deterministic fake tests or compilation."""
        workflow = (
            "jobs:\n  test:\n    steps:\n      - run: |\n"
            "          python3 -m unittest discover -s tests -v\n"
            "          python3 -m py_compile evals/harness/run.py\n"
            "          python3 -m compileall -q evals/harness\n"
            "          env PYTHONPYCACHEPREFIX=/tmp/ci python3 -m unittest discover -s tests -v\n"
        )
        self.assertEqual(unsafe_ci_commands(workflow), ())


if __name__ == "__main__":
    unittest.main()


class MirrorGuardCoverageTest(unittest.TestCase):
    """Every shipped script and resource in the skill directory must have a
    byte-identical root mirror, and the JSON depth bound must exist wherever
    untrusted JSON is parsed — the interpreter no longer supplies one."""

    def test_all_skill_scripts_have_byte_identical_root_mirrors(self):
        skill_scripts = ROOT / "skills" / "requirements-impact-refiner" / "scripts"
        for path in sorted(skill_scripts.iterdir()):
            if path.name == "__pycache__":
                continue
            with self.subTest(script=path.name):
                mirror = ROOT / "scripts" / path.name
                self.assertTrue(mirror.is_file(), mirror)
                self.assertEqual(mirror.read_bytes(), path.read_bytes(), path.name)

    def test_untrusted_json_parsers_carry_an_explicit_depth_bound(self):
        consumers = (
            "rir_mcp_server.py",
            "rir-controller.py",
            "fast_scan_store.py",
            "graph_providers.py",
            "graph_adapter_joern.py",
            "graph_adapter_ast_grep.py",
            "impact_graph.py",
            "graph_cache.py",
        )
        for name in consumers:
            with self.subTest(script=name):
                text = (ROOT / "scripts" / name).read_text()
                self.assertIn("_MAX_JSON_DEPTH", text, name)
                self.assertIn("_json_depth(", text, name)
