import json
import re
import shlex
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_COMPONENTS = {"mcpServers", "apps", "hooks", "agents", "dependencies"}


def ci_run_commands(workflow_text):
    """Extract executable shell content from GitHub Actions ``run`` steps."""
    lines = workflow_text.splitlines()
    commands = []
    index = 0
    while index < len(lines):
        match = re.match(
            r"^(?P<indent>\s*)(?:-\s+)?run:\s*(?P<content>.*)$", lines[index]
        )
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
            if re.fullmatch(
                r"python(?:\d+(?:\.\d+)*)?", Path(argument).name
            ):
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
    if command == "brew" and {"install", "--cask", "claude-code"}.issubset(
        arguments
    ):
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
        raise AssertionError("unsafe CI run command(s): %r" % (unsafe,))


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
        self.assertEqual(manifest["version"], "0.3.2")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertTrue(FORBIDDEN_COMPONENTS.isdisjoint(manifest))

    def test_claude_manifest_uses_default_skill_location(self):
        manifest = self.load(".claude-plugin/plugin.json")
        self.assertEqual(manifest["name"], "requirements-impact-refiner")
        self.assertEqual(manifest["version"], "0.3.2")
        self.assertTrue(FORBIDDEN_COMPONENTS.isdisjoint(manifest))

    def test_automatic_bootstrap_skill_is_discoverable(self):
        path = ROOT / "skills/using-requirements-impact-refiner/SKILL.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("name: using-requirements-impact-refiner", text)
        self.assertIn("Use when starting any software-development conversation", text)
        self.assertIn('version: "0.3.2"', text)

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

    def test_stage_templates_are_disjoint_and_complete(self):
        assets = ROOT / "skills/requirements-impact-refiner/assets"
        chooser = (assets / "impact-report-template.md").read_text(encoding="utf-8")
        pre = (assets / "impact-report-pre-decision-template.md").read_text(
            encoding="utf-8"
        )
        post = (assets / "impact-report-post-decision-template.md").read_text(
            encoding="utf-8"
        )

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
            self.assertIn(
                "| Report ID | Revision | Previous SHA-256 | Phase |", text
            )
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

    def test_plugin_root_resource_fallback_mirrors_are_complete_and_identical(self):
        """Plugin-root fallbacks must exactly preserve canonical skill resources."""
        canonical = ROOT / "skills" / "requirements-impact-refiner"
        mirror_contract = {
            "references": set(),
            "assets": {Path("logo.png")},
            "scripts": {Path("install-agent-skill.py")},
            "schemas": set(),
        }

        for directory, root_only_files in mirror_contract.items():
            canonical_dir = canonical / directory
            canonical_files = {
                path.relative_to(canonical_dir)
                for path in canonical_dir.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            }
            mirror_dir = ROOT / directory
            mirror_files = {
                path.relative_to(mirror_dir)
                for path in mirror_dir.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            }

            self.assertEqual(mirror_files, canonical_files | root_only_files)
            for relative_path in canonical_files:
                self.assertEqual(
                    (mirror_dir / relative_path).read_bytes(),
                    (canonical_dir / relative_path).read_bytes(),
                    f"{directory}/{relative_path} must be byte-identical to canonical",
                )

        self.assertFalse((ROOT / "SKILL.md").exists())

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
        core = (ROOT / "skills/requirements-impact-refiner/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "Resolve every `references/`, `assets/`, and `scripts/` path from the directory that contains this `SKILL.md`.",
            core,
        )
        self.assertIn(
            "read `SKILL_DIR/references/evidence-model.md`", core,
        )
        self.assertIn("not the plugin root or workspace root", core)
        self.assertIn(
            "Byte-identical plugin-root mirrors are fallback only if a client loses or misinfers `SKILL_DIR`",
            core,
        )

    def test_core_skill_requires_an_inline_canonical_report(self):
        core = (ROOT / "skills/requirements-impact-refiner/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "first non-empty line exactly `# Requirements Impact Report`", core
        )
        self.assertIn("complete canonical current report inline", core)
        self.assertIn("saved file is supplementary only", core)
        self.assertIn("lineage turn returns the complete revised report inline", core)

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
                    "jobs:\n  test:\n    steps:\n      - run: |\n          %s\n" % command,
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(AssertionError, "unsafe CI run command"):
                    assert_safe_ci_workflow(workflow_path.read_text(encoding="utf-8"))

    def test_ci_safety_ignores_non_executable_claude_mentions(self):
        self.assertEqual(
            unsafe_ci_commands(
                "Documentation may discuss `claude auth` outside a CI run step.\n"
            ),
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
