#!/usr/bin/env python3
"""Deterministic, bounded lexical fallback for repository impact discovery."""

from __future__ import annotations

from dataclasses import dataclass
import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import stat
import sys
from types import MappingProxyType
from typing import Mapping, Sequence


def _load_graph_contract():
    name = "_rir_impact_graph"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = Path(__file__).with_name("impact_graph.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load impact graph contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GRAPH = _load_graph_contract()
GraphNode = GRAPH.GraphNode
GraphEdge = GRAPH.GraphEdge
GraphPath = GRAPH.GraphPath
FrontierEntry = GRAPH.FrontierEntry

DEFAULT_MAX_FILE_BYTES = 1_048_576
MAX_GRAPH_ID = 999
IGNORED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".requirements-impact-refiner",
    "vendor", "build", "dist", "generated",
    "node_modules", ".next", ".venv", "venv", "target", "coverage",
})
# The left boundary forbids starting inside an alphanumeric run: without
# it the engine retries every offset of a long base64 blob and a single
# transcript line costs seconds (observed 3.4 s -> 2.8 ms on 140 KB).
_DOTTED = re.compile(
    r"(?<![A-Za-z0-9_.])[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
)
_SLASHED = re.compile(
    r"(?<![A-Za-z0-9_./-])[A-Za-z_][A-Za-z0-9_.-]*(?:/[A-Za-z_][A-Za-z0-9_.-]*)+"
)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_QUOTED = re.compile(r"(?P<quote>['\"])(?P<value>[^'\"\r\n]{2,256})(?P=quote)")
_IMPORT = re.compile(r"(?m)^\s*(?:from|import)\s+(?P<value>[^\r\n#]+)")
_PYTHON_FROM_IMPORT = re.compile(
    r"(?m)^[ \t]*from[ \t]+(?P<module>[.A-Za-z_][A-Za-z0-9_.]*)"
    r"[ \t]+import\b"
)
_PYTHON_IMPORT = re.compile(r"(?m)^[ \t]*import[ \t]+(?P<modules>[^\r\n#;]+)")
_JS_FROM_IMPORT = re.compile(
    r"(?ms)^[ \t]*import\b(?:(?!;).){0,4096}?\bfrom[ \t\r\n]+"
    r"(?P<quote>['\"])(?P<module>[^'\"\r\n]+)(?P=quote)"
)
_JS_SIDE_EFFECT_IMPORT = re.compile(
    r"(?m)^[ \t]*import[ \t]+(?P<quote>['\"])(?P<module>[^'\"\r\n]+)"
    r"(?P=quote)"
)
_YAML_BLOCK_INDICATOR = re.compile(r"[ \t]*(?P<indicator>[|>][+-]?)[^\r\n]*(?:\r\n|\r|\n)")
# Credential-shaped names are matched as whole identifier segments — snake,
# kebab, and camel case, with prefixes and suffixes (GITHUB_TOKEN,
# stripeSecretKey, tokenProd) — while embedded fragments (tokenizer,
# keyboard) are preserved. The assignment operator also covers := so a
# walrus or Go declaration cannot strand the literal outside the match.
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(?P<prefix>(?<![A-Za-z0-9_])(?P<keyquote>['\"]?)"
    r"(?:[A-Za-z0-9]+[_-]|(?-i:[A-Z]?[a-z0-9]+(?=[A-Z])))*"
    r"(?:aws[_-]secret[_-]access[_-]key|client[_-]?secret|access[_-]?token|"
    r"refresh[_-]?token|auth[_-]?token|api[_-]?key|api[_-]?secret|"
    r"private[_-]key|secret[_-]?key|token|password|passwd|passphrase|secret|"
    r"credential)"
    r"(?:[_-][A-Za-z0-9]+|(?-i:[A-Z][A-Za-z0-9]*))*"
    r"(?P=keyquote)\s*(?::=|[:=])\s*)"
)
_COMMON_TERMS = frozenset({
    "assert", "class", "const", "def", "export", "from", "function",
    "import", "interface", "profile", "return", "static", "string", "struct",
    "target", "tests", "true", "value",
})
_RISK_ORDER = (
    "authorization/privacy", "interfaces", "data", "state/concurrency",
    "compatibility", "operations", "regression", "functionality",
    "legal/policy",
)
_RISK_RANK = {name: index for index, name in enumerate(_RISK_ORDER)}


@dataclass(frozen=True)
class ScanSeed:
    term: str
    location: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.term, str) or not self.term.strip() or len(self.term) > GRAPH.MAX_STRING_LENGTH:
            raise ValueError("scan seed term must be a bounded non-empty string")
        if self.location is not None and not GRAPH._safe_path(self.location):
            raise ValueError("scan seed location must be a safe repository-relative path")


@dataclass(frozen=True)
class ScanLimits:
    max_seconds: int = 30
    max_files: int = 500
    max_bytes: int = 8_000_000
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_nodes: int = min(GRAPH.MAX_NODES, MAX_GRAPH_ID)
    max_edges: int = min(GRAPH.MAX_EDGES, MAX_GRAPH_ID)
    max_paths: int = min(GRAPH.MAX_PATHS, MAX_GRAPH_ID)

    def __post_init__(self) -> None:
        for name in (
            "max_seconds", "max_files", "max_bytes", "max_file_bytes",
            "max_nodes", "max_edges", "max_paths",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.max_seconds > 30:
            raise ValueError("max_seconds must not exceed 30")
        if self.max_file_bytes > DEFAULT_MAX_FILE_BYTES:
            raise ValueError("max_file_bytes must not exceed 1 MiB")
        for name, maximum in (
            ("max_nodes", min(GRAPH.MAX_NODES, MAX_GRAPH_ID)),
            ("max_edges", min(GRAPH.MAX_EDGES, MAX_GRAPH_ID)),
            ("max_paths", min(GRAPH.MAX_PATHS, MAX_GRAPH_ID)),
        ):
            if getattr(self, name) > maximum:
                raise ValueError(f"{name} exceeds graph contract three-digit ID maximum")


@dataclass(frozen=True)
class BuiltInScanResult:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    paths: tuple[GraphPath, ...]
    frontier: tuple[FrontierEntry, ...]
    source_digests: Mapping[str, str]
    skipped: Mapping[str, str]
    files_scanned: int
    bytes_scanned: int
    budget_status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "paths", tuple(self.paths))
        object.__setattr__(self, "frontier", tuple(self.frontier))
        object.__setattr__(self, "source_digests", MappingProxyType(dict(self.source_digests)))
        object.__setattr__(self, "skipped", MappingProxyType(dict(self.skipped)))


def _empty_result(status="closed"):
    return BuiltInScanResult((), (), (), (), {}, {}, 0, 0, status)


# Risk keywords match whole identifier tokens (camel boundaries split),
# never substrings: an npm author field, a JSX role attribute, or a
# tokenizer must not classify a file as an authorization risk and
# escalate the scan to critical.
_RISK_DOMAIN_PATTERNS = {
    "authorization/privacy": re.compile(
        r"auth(?:z|n|orization|oriz\w+|entic\w+)?|oauth|permissions?|"
        r"privacy|tokens?|credentials?|roles|acl|rbac"
    ),
    "interfaces": re.compile(r"apis?|schemas?|dtos?|interfaces?"),
    "data": re.compile(r"data|database|db|migrations?|serializ\w*"),
    "state/concurrency": re.compile(
        r"cached?|caches|states?|stateful|locks?|locking|locked|"
        r"concurr\w*|mutex"
    ),
    "compatibility": re.compile(r"mobile|desktop|compat\w*|migrations?"),
    "operations": re.compile(
        r"events?|deploy\w*|configs?|configuration|queues?"
    ),
    "regression": re.compile(
        r"tests?|testing|conftest|fixtures?|migrations?"
    ),
}
_CAMEL_BOUNDARY = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)


def _risk_domains(location: str | None, text: str = "") -> tuple[str, ...]:
    haystack = _CAMEL_BOUNDARY.sub(" ", (location or "") + " " + text).lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", haystack) if token}
    domains = set()
    for domain, pattern in _RISK_DOMAIN_PATTERNS.items():
        if any(pattern.fullmatch(token) for token in tokens):
            domains.add(domain)
    if not domains:
        domains.add("functionality")
    return tuple(sorted(domains, key=lambda item: (_RISK_RANK[item], item)))


def _node_kind(location: str | None, text: str) -> str:
    haystack = ((location or "") + " " + text).lower()
    if "test" in haystack or "fixture" in haystack:
        return "test"
    if any(term in haystack for term in ("auth", "permission", "privacy")):
        return "permission"
    if "event" in haystack:
        return "event"
    if "cache" in haystack:
        return "cache"
    if "config" in haystack:
        return "configuration"
    if "api" in haystack or "dto" in haystack:
        return "api_field"
    return "file"


def _expanded_terms(values) -> frozenset[str]:
    expanded = set(values)
    for value in tuple(expanded):
        expanded.update(part for part in re.split(r"[./]", value) if len(part) >= 4)
        if "." in value:
            expanded.add(value.replace(".", "/"))
        if "/" in value:
            expanded.add(value.replace("/", "."))
    return frozenset(
        value for value in expanded
        if len(value) >= 4 and value.lower() not in _COMMON_TERMS
    )


def _safe_graph_text(value: str, sensitive_literals=()) -> str:
    if value in sensitive_literals:
        return "sensitive-sha256-" + hashlib.sha256(value.encode("utf-8")).hexdigest()
    return value


def _value_expression_end(rest: str) -> int:
    """Index where the credential's value expression ends: the first
    top-level comma, closing brace/bracket, or comment start outside quotes,
    tracking nesting so wrapped calls and container literals stay inside."""
    depth = 0
    quote = None
    escaped = False
    for index, char in enumerate(rest):
        if quote is not None:
            if escaped:
                escaped = False
                continue
            if char == "\\" and quote != "`":
                escaped = True
                continue
            if char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                return index
            depth -= 1
        elif depth == 0 and char in ",;#\r\n":
            return index
        elif depth == 0 and rest[index:index + 2] == "//":
            return index
    return len(rest)


def _redact_quoted_literals(value_text: str, sensitive: set[str]) -> tuple[str, int]:
    output = []
    cursor = 0
    count = 0
    while cursor < len(value_text):
        quote = value_text[cursor]
        if quote not in "'\"`":
            output.append(quote)
            cursor += 1
            continue
        end = cursor + 1
        escaped = False
        while end < len(value_text):
            char = value_text[end]
            if escaped:
                escaped = False
            elif char == "\\" and quote != "`":
                escaped = True
            elif char == quote:
                break
            end += 1
        if end >= len(value_text):
            output.append(value_text[cursor:])
            break
        value = value_text[cursor + 1:end]
        sensitive.add(value)
        output.extend((
            quote,
            _safe_graph_text(value, (value,)),
            quote,
        ))
        count += 1
        cursor = end + 1
    return "".join(output), count


def _yaml_block_span(
    text: str, value_start: int, assignment_start: int
) -> tuple[int, int] | None:
    indicator = _YAML_BLOCK_INDICATOR.match(text, value_start)
    if indicator is None:
        return None
    line_start = text.rfind("\n", 0, assignment_start) + 1
    base_indent = len(text[line_start:assignment_start])
    cursor = indicator.end()
    end = cursor
    while cursor < len(text):
        line_end = text.find("\n", cursor)
        line_end = len(text) if line_end < 0 else line_end + 1
        line = text[cursor:line_end]
        if line.strip():
            indent = len(line) - len(line.lstrip(" \t"))
            if indent <= base_indent:
                break
        end = line_end
        cursor = line_end
    return indicator.end(), end


def _redact_sensitive_literals(text: str) -> tuple[str, frozenset[str]]:
    sensitive = set()
    output = []
    cursor = 0
    for match in _SENSITIVE_ASSIGNMENT.finditer(text):
        if match.start() < cursor:
            continue
        output.append(text[cursor:match.end()])
        yaml_span = _yaml_block_span(text, match.end(), match.start())
        if yaml_span is not None:
            content_start, end = yaml_span
            block = text[content_start:end]
            value = block.strip()
            sensitive.add(value)
            indent = re.match(r"[ \t]*", block).group(0) if block else ""
            newline = "\n" if block.endswith(("\n", "\r")) else ""
            output.append(text[match.end():content_start])
            output.append(indent + _safe_graph_text(value, (value,)) + newline)
            cursor = end
            continue
        rest = text[match.end():]
        span = _value_expression_end(rest)
        value_text = rest[:span]

        # Every quoted literal inside the credential's value expression is
        # redacted, so wrapped forms — []byte("..."), map{...: "..."},
        # getenv(_, "..."), multiline values, escaped quotes, and Go raw
        # strings — cannot strand the secret. Literals past the expression
        # boundary (sibling JSON keys) are left intact.
        redacted, quoted_count = _redact_quoted_literals(value_text, sensitive)
        if quoted_count == 0:
            bare = re.match(r"[^\s,#})\]]+", value_text)
            if bare is None:
                redacted = value_text
            else:
                value = bare.group(0)
                sensitive.add(value)
                redacted = (
                    _safe_graph_text(value, (value,)) + value_text[bare.end():]
                )
        output.append(redacted)
        cursor = match.end() + span
    output.append(text[cursor:])
    return "".join(output), frozenset(sensitive)


def _term_categories(text: str) -> Mapping[str, frozenset[str]]:
    values = set()
    values.update(_DOTTED.findall(text))
    values.update(_SLASHED.findall(text))
    values.update(_IDENTIFIER.findall(text))
    values.update(match.group("value") for match in _QUOTED.finditer(text))
    categories = {value: {"lexical"} for value in _expanded_terms(values)}
    imports = set()
    for match in _IMPORT.finditer(text):
        import_text = match.group("value")
        imports.update(_DOTTED.findall(import_text))
        imports.update(_IDENTIFIER.findall(import_text))
    for value in _expanded_terms(imports):
        categories.setdefault(value, set()).add("import")
    return MappingProxyType({
        value: frozenset(categories[value]) for value in sorted(categories)
    })


def _without_javascript_comments(text: str) -> str:
    """Replace JS/TS comments with spaces while preserving strings/newlines."""
    output = list(text)
    quote = None
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"`":
            quote = char
            index += 1
            continue
        if text[index:index + 2] == "//":
            end = text.find("\n", index + 2)
            end = len(text) if end < 0 else end
            for cursor in range(index, end):
                output[cursor] = " "
            index = end
            continue
        if text[index:index + 2] == "/*":
            end = text.find("*/", index + 2)
            end = len(text) if end < 0 else end + 2
            for cursor in range(index, end):
                if output[cursor] not in "\r\n":
                    output[cursor] = " "
            index = end
            continue
        index += 1
    return "".join(output)


def _javascript_code_mask(text: str) -> tuple[bool, ...]:
    """True where a JS/TS token starts outside strings and comments."""
    mask = [True] * len(text)
    quote = None
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            mask[index] = False
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"`":
            quote = char
            mask[index] = False
            index += 1
            continue
        if text[index:index + 2] == "//":
            end = text.find("\n", index + 2)
            end = len(text) if end < 0 else end
            for cursor in range(index, end):
                mask[cursor] = False
            index = end
            continue
        if text[index:index + 2] == "/*":
            end = text.find("*/", index + 2)
            end = len(text) if end < 0 else end + 2
            for cursor in range(index, end):
                mask[cursor] = False
            index = end
            continue
        index += 1
    return tuple(mask)


def _import_modules(text: str) -> frozenset[str]:
    """Collapsed module-path tokens from import statements. Only these can
    justify an imports edge: an imported member name (from helpers import
    auth) must not structurally link an unrelated file carrying that name."""
    modules = set()

    def add_specifier(specifier: str) -> None:
        cleaned = specifier.strip().strip("'\"").lstrip("./")
        if not cleaned:
            return
        parts = [part for part in re.split(r"[./\\\\]+", cleaned) if part]
        if parts and re.fullmatch(r"(?:py|js|jsx|ts|tsx|mjs|cjs)", parts[-1], re.I):
            parts.pop()
        values = [parts[-1], "".join(parts)] if parts else []
        for value in values:
            collapsed = re.sub(r"[^a-z0-9]", "", value.lower())
            if len(collapsed) >= 3:
                modules.add(collapsed)

    for match in _PYTHON_FROM_IMPORT.finditer(text):
        add_specifier(match.group("module"))
    javascript_text = _without_javascript_comments(text)
    javascript_code = _javascript_code_mask(text)
    for pattern in (_JS_FROM_IMPORT, _JS_SIDE_EFFECT_IMPORT):
        for match in pattern.finditer(javascript_text):
            if javascript_code[match.start()]:
                add_specifier(match.group("module"))
    for match in _PYTHON_IMPORT.finditer(text):
        for clause in match.group("modules").split(","):
            specifier = re.split(r"\s+as\s+", clause.strip(), maxsplit=1)[0]
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", specifier):
                add_specifier(specifier)
    return frozenset(modules)


class LanguageStructure:
    """Genuine structure for a source file: import module specifiers,
    defined names, and used names. None when the source cannot be
    analyzed — the scan then falls back to lexical evidence honestly."""

    __slots__ = ("modules", "defs", "uses")

    def __init__(self, modules, defs, uses):
        self.modules = modules
        self.defs = defs
        self.uses = uses


_SCRIPT_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
_JS_EXPORT = re.compile(
    r"(?m)^\s*export\s+(?:default\s+)?"
    r"(?:async\s+)?(?:function\*?|class|const|let|var)\s+"
    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]{2,})"
)
_JS_COMMONJS_EXPORT = re.compile(
    r"(?:module\.)?exports\.(?P<name>[A-Za-z_$][A-Za-z0-9_$]{2,})\s*="
)
_JS_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]{2,}")


def _javascript_structure(text: str):
    """Structural signals for script-family files: exported names are
    definitions, identifiers in masked code are uses. Comments and string
    literals never contribute — the mask excludes them."""
    masked = _without_javascript_comments(text)
    code = _javascript_code_mask(text)
    defs = set()
    uses = set()
    for pattern in (_JS_EXPORT, _JS_COMMONJS_EXPORT):
        for match in pattern.finditer(masked):
            if code[match.start("name")]:
                defs.add(match.group("name"))
    for match in _JS_IDENTIFIER.finditer(masked):
        if code[match.start()]:
            uses.add(match.group(0))
    uses -= defs
    return LanguageStructure(_import_modules(text), frozenset(defs), frozenset(uses))


def _python_structure(text: str):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return None
    specifiers = []
    defs = set()
    loads = set()
    stores = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            specifiers.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # Relative imports resolve within the repository too; a bare
            # "from . import x" names its submodules directly.
            if node.module:
                specifiers.append(node.module)
            elif node.level:
                specifiers.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                loads.add(node.id)
            else:
                stores.add(node.id)
    # The definition surface is the module's top level — functions, classes,
    # and module constants. Function locals are not cross-file API and made
    # every shared variable name (result, payload) a false structural edge.
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.add(node.name)
        elif isinstance(node, ast.Assign):
            for target_node in node.targets:
                if isinstance(target_node, ast.Name):
                    defs.add(target_node.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                defs.add(node.target.id)
    # A name the file itself binds anywhere is a local use, not evidence of
    # depending on another file's definition.
    uses = loads - stores
    modules = set()
    for specifier in specifiers:
        parts = [part for part in specifier.split(".") if part]
        for value in ([parts[-1], "".join(parts)] if parts else []):
            collapsed = re.sub(r"[^a-z0-9]", "", value.lower())
            if len(collapsed) >= 3:
                modules.add(collapsed)
    minimum = 3
    return LanguageStructure(
        frozenset(modules),
        frozenset(name for name in defs if len(name) >= minimum),
        frozenset(name for name in uses if len(name) >= minimum),
    )


def _terms(text: str) -> frozenset[str]:
    return frozenset(_term_categories(text))


def _open_below_root(root: Path, relative: str) -> int:
    """Open relative under root with a per-component descriptor walk, so a
    parent directory swapped for a symlink after the walk check cannot pull
    out-of-repo content into the scan."""
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    file_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
        file_flags |= os.O_NOFOLLOW
    parts = [part for part in relative.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("unsafe relative path")
    parent = os.open(str(root), directory_flags)
    try:
        for part in parts[:-1]:
            next_parent = os.open(part, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = next_parent
        return os.open(parts[-1], file_flags, dir_fd=parent)
    finally:
        os.close(parent)


def _read_regular_file(
    root: Path, relative: str, maximum: int, remaining: int | None = None,
    read_allowed: bool = True,
) -> tuple[bytes | None, str | None]:
    try:
        descriptor = _open_below_root(root, relative)
    except (OSError, ValueError):
        return None, "unsafe-file"
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return None, "not-regular"
        if metadata.st_size > maximum:
            return None, "oversized"
        if remaining is not None and metadata.st_size > remaining:
            return None, "byte-limit"
        if not read_allowed:
            return None, "file-limit"
        read_limit = min(maximum, remaining) if remaining is not None else maximum
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read(read_limit + 1)
        if len(payload) > maximum:
            return None, "oversized"
        if remaining is not None and len(payload) > remaining:
            return None, "byte-limit"
        return payload, None
    finally:
        os.close(descriptor)


def _walk_files(
    root: Path, expired, skipped: dict[str, str], traversal_errors: list[str]
):
    pending = [root]
    while pending:
        if expired():
            return
        directory = pending.pop(0)
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            traversal_errors.append(directory.relative_to(root).as_posix())
            continue
        directories = []
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            if entry.is_symlink():
                skipped[relative] = "symlink"
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in IGNORED_DIRECTORIES:
                        directories.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path), relative
            except OSError:
                skipped[relative] = "unsafe-file"
                traversal_errors.append(relative)
        pending[0:0] = directories


_TEST_PATH_TOKENS = frozenset(
    {"test", "tests", "testing", "conftest", "fixture", "fixtures"}
)


def _is_test_path(target: str) -> bool:
    """Match whole path segments so latest/contest/testimonial stay untouched."""
    for part in target.lower().split("/"):
        for token in re.split(r"[^a-z0-9]+", part):
            if token in _TEST_PATH_TOKENS:
                return True
    return False


def _import_resolves_to_target(target: str, evidence: str) -> bool:
    """An edge earns structural confidence only when the evidence token
    plausibly names the target file — exact collapsed equality or a whole
    stem segment, never a substring, which collides (config in
    reconfigure)."""
    stem = target.lower().rsplit("/", 1)[-1].split(".", 1)[0]
    collapsed_stem = re.sub(r"[^a-z0-9]", "", stem)
    collapsed_evidence = re.sub(r"[^a-z0-9]", "", evidence.lower())
    if len(collapsed_evidence) < 3 or not collapsed_stem:
        return False
    if collapsed_evidence == collapsed_stem:
        return True
    segments = {part for part in re.split(r"[^a-z0-9]+", stem) if part}
    return collapsed_evidence in segments


def _module_resolves_to_target(target: str, modules: frozenset[str]) -> bool:
    stem = target.lower().rsplit("/", 1)[-1].split(".", 1)[0]
    collapsed_stem = re.sub(r"[^a-z0-9]", "", stem)
    if not collapsed_stem:
        return False
    segments = {part for part in re.split(r"[^a-z0-9]+", stem) if part}
    return any(
        module == collapsed_stem or module in segments
        for module in modules
    )


def _edge_kind(
    target: str, modules: frozenset[str], evidence: str, basis: str
) -> tuple[str, str]:
    if _is_test_path(target):
        # A test-shaped filename alone is a lexical coincidence; structural
        # confidence requires a structural basis or evidence naming the
        # target.
        structural = basis != "lexical" or _import_resolves_to_target(
            target, evidence
        )
        return "tests", "structural-inferred" if structural else "lexical"
    if basis == "import":
        return "imports", "structural-inferred"
    if basis == "defuse":
        return "references", "structural-inferred"
    return "references", "lexical"


def _path_sort_key(path_data, node_risks):
    node_ids, _ = path_data
    domains = {domain for node_id in node_ids for domain in node_risks[node_id]}
    best = min((_RISK_RANK[domain] for domain in domains), default=len(_RISK_ORDER))
    return best, len(node_ids) - 1, node_ids


def scan_repository(
    repo_root: Path | str,
    seeds: Sequence[ScanSeed],
    limits: ScanLimits,
    clock,
) -> BuiltInScanResult:
    """Scan regular UTF-8 source files without crossing any supplied bound."""
    root = Path(repo_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("repo_root must be a regular directory")
    root = root.resolve()
    normalized_seeds = tuple(sorted(set(seeds), key=lambda item: (item.location or "", item.term)))
    if any(not isinstance(seed, ScanSeed) for seed in normalized_seeds):
        raise TypeError("seeds must contain ScanSeed values")
    if not isinstance(limits, ScanLimits):
        raise TypeError("limits must be ScanLimits")
    started = clock.monotonic()
    deadline = started + limits.max_seconds

    def expired():
        return clock.monotonic() >= deadline

    if expired():
        return _empty_result("budget_exhausted")

    skipped: dict[str, str] = {}
    traversal_errors: list[str] = []
    documents: dict[str, tuple] = {}
    sensitive_literals = set()
    bytes_scanned = 0
    files_scanned = 0
    exhausted = False
    for path, relative in _walk_files(root, expired, skipped, traversal_errors):
        if expired():
            exhausted = True
            break
        remaining = limits.max_bytes - bytes_scanned
        payload, reason = _read_regular_file(
            root, relative, limits.max_file_bytes, remaining,
            read_allowed=files_scanned < limits.max_files,
        )
        if reason is not None or payload is None:
            skipped[relative] = reason or "unsafe-file"
            if reason in {"oversized", "byte-limit", "file-limit"}:
                exhausted = True
            continue
        if len(payload) > remaining:
            skipped[relative] = "byte-limit"
            exhausted = True
            continue
        files_scanned += 1
        bytes_scanned += len(payload)
        if b"\x00" in payload:
            skipped[relative] = "binary"
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            skipped[relative] = "invalid-utf8"
            continue
        safe_text, found_sensitive = _redact_sensitive_literals(text)
        sensitive_literals.update(found_sensitive)
        categories = _term_categories(safe_text)
        if relative.endswith(".py"):
            structure = _python_structure(safe_text)
        elif relative.endswith(_SCRIPT_SUFFIXES):
            structure = _javascript_structure(safe_text)
        else:
            structure = None
        modules = (
            structure.modules if structure is not None
            else _import_modules(safe_text)
        )
        documents[relative] = (
            safe_text, frozenset(categories), hashlib.sha256(payload).hexdigest(),
            categories, modules, structure,
        )

    if expired():
        exhausted = True

    unreadable_sources = sorted(
        path for path, reason in skipped.items() if reason == "unsafe-file"
    )

    def deadline_result(nodes=(), edges=()):
        frontier = ()
        if nodes:
            last = nodes[-1]
            frontier = (
                FrontierEntry(
                    "FRONTIER-001", last.id, "built-in scan deadline exhausted",
                    last.risk_domains,
                ),
            )
        return BuiltInScanResult(
            tuple(nodes), tuple(edges), (), frontier,
            {location: documents[location][2] for location in sorted(documents)},
            {path: skipped[path] for path in sorted(skipped)},
            files_scanned, bytes_scanned, "budget_exhausted",
        )

    if exhausted and expired():
        return deadline_result()

    seed_locations = {seed.location for seed in normalized_seeds if seed.location in documents}
    seed_terms = {term for seed in normalized_seeds for term in _terms(seed.term)}
    if not seed_terms:
        seed_terms = {seed.term for seed in normalized_seeds}

    relationships = []
    locations = sorted(documents)
    for source in locations:
        source_terms = documents[source][1]
        source_modules = documents[source][4]
        source_structure = documents[source][5]
        for target in locations:
            if expired():
                return deadline_result()
            if source == target:
                continue
            # 1) A parsed or declared import resolving to the target file is
            #    structural evidence and needs no token co-occurrence. A
            #    python import can only land on a python file — a document
            #    whose stem merely contains the module name is not a module.
            if source.endswith(".py"):
                plausible_import_target = target.endswith(".py")
            elif source.endswith(_SCRIPT_SUFFIXES):
                plausible_import_target = target.endswith(
                    _SCRIPT_SUFFIXES + (".json",)
                )
            else:
                plausible_import_target = True
            if plausible_import_target and _module_resolves_to_target(
                target, source_modules
            ):
                stem = target.lower().rsplit("/", 1)[-1].split(".", 1)[0]
                relationships.append(
                    (source, target, stem, source_modules, "import")
                )
                continue
            # 2) Using a name the target genuinely defines (both sides
            #    parsed) is structural; string mentions never reach here
            #    because ast defs/uses exclude literals.
            target_structure = documents[target][5]
            if source_structure is not None and target_structure is not None:
                used_defs = source_structure.uses & target_structure.defs
                if used_defs:
                    evidence = min(
                        used_defs, key=lambda value: (-len(value), value)
                    )
                    relationships.append(
                        (source, target, evidence, source_modules, "defuse")
                    )
                    continue
            # 3) Shared-token co-occurrence stays lexical.
            shared = source_terms & documents[target][1]
            if shared:
                # min under (-len, value) == longest token, ties lexicographic
                # — identical pick to the previous full sort, without paying
                # an O(k log k) sort for every ordered file pair.
                evidence = min(shared, key=lambda value: (-len(value), value))
                relationships.append(
                    (source, target, evidence, source_modules, "lexical")
                )

    reachable = set(seed_locations)
    reachable.update(
        location for location, (_, terms, *_rest) in documents.items()
        if terms & seed_terms
    )
    changed = True
    while changed and not expired():
        changed = False
        for source, target, _, _, _ in relationships:
            if expired():
                exhausted = True
                break
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
    if expired():
        return deadline_result()

    supplied_only = [seed for seed in normalized_seeds if seed.location is None or seed.location not in documents]
    ordered_locations = sorted(
        reachable,
        key=lambda location: (
            0 if location in seed_locations else 1,
            min((_RISK_RANK[item] for item in _risk_domains(location, documents[location][0])), default=99),
            location,
        ),
    )
    all_error_locations = sorted(set(traversal_errors))
    error_limit = (
        GRAPH.MAX_FRONTIER - 1
        if len(all_error_locations) > GRAPH.MAX_FRONTIER
        else GRAPH.MAX_FRONTIER
    )
    error_locations = all_error_locations[:error_limit]
    matched_locations = [
        location for location in ordered_locations if location in seed_locations
    ]
    remaining_locations = [
        location for location in ordered_locations if location not in seed_locations
    ]
    candidates = [(location, None, False) for location in matched_locations]
    candidates.extend((None, seed, False) for seed in supplied_only)
    candidates.extend((location, None, False) for location in remaining_locations)
    candidates.extend((location, None, True) for location in error_locations)
    if len(candidates) > limits.max_nodes:
        exhausted = True
    candidates = candidates[:limits.max_nodes]

    nodes = []
    location_ids = {}
    error_node_ids = {}
    node_risks = {}
    for index, (location, seed, is_error) in enumerate(candidates, start=1):
        if expired():
            return deadline_result(nodes)
        node_id = f"NODE-{index:03d}"
        if is_error:
            safe_location = None if location == "." else location
            label = "unreadable repository directory"
            risk = ("functionality",)
            node = GraphNode(
                node_id, "file", label, safe_location, "builtin", "lexical",
                None, risk,
            )
            error_node_ids[location] = node_id
        elif location is None:
            label = _safe_graph_text(seed.term, sensitive_literals)
            risk = _risk_domains(seed.location, seed.term)
            node = GraphNode(node_id, "symbol", label, seed.location, "builtin", "lexical", None, risk)
        else:
            text, _, digest, *_rest = documents[location]
            risk = _risk_domains(location, text)
            label = next((
                _safe_graph_text(seed.term, sensitive_literals)
                for seed in normalized_seeds if seed.location == location
            ), location)
            confidence = "structural-inferred" if location in seed_locations else "lexical"
            node = GraphNode(node_id, _node_kind(location, text), label, location, "builtin", confidence, digest, risk)
            location_ids[location] = node_id
        nodes.append(node)
        node_risks[node_id] = risk

    if unreadable_sources and not nodes and limits.max_nodes > 0:
        node = GraphNode(
            "NODE-001", "file", "unreadable source",
            unreadable_sources[0], "builtin", "lexical", None,
            ("functionality",),
        )
        nodes.append(node)
        node_risks[node.id] = node.risk_domains

    edge_candidates = []
    for source, target, evidence, modules, basis in relationships:
        if expired():
            return deadline_result(nodes)
        if source in location_ids and target in location_ids:
            kind, confidence = _edge_kind(target, modules, evidence, basis)
            edge_candidates.append((source, target, kind, confidence, evidence))
    # Structural evidence outranks lexical co-occurrence when the edge cap
    # bites: a large repository must not lose exactly the edges the scan
    # exists to find. Ordering stays deterministic within each tier.
    edge_candidates.sort(key=lambda item: (
        0 if item[3] == "structural-inferred" else 1,
        location_ids[item[0]], location_ids[item[1]], item[2], item[4],
    ))
    if len(edge_candidates) > limits.max_edges:
        exhausted = True
    edge_candidates = edge_candidates[:limits.max_edges]
    edges = []
    adjacency = {}
    for index, (source, target, kind, confidence, evidence) in enumerate(edge_candidates, start=1):
        if expired():
            return deadline_result(nodes, edges)
        edge_id = f"EDGE-{index:03d}"
        # An imports edge is evidenced by the import statement in the source
        # file; every other kind is evidenced by the shared occurrence in the
        # target. Provenance records where the evidence actually lives.
        evidence_location = source if kind == "imports" else target
        edge = GraphEdge(
            edge_id, location_ids[source], location_ids[target], kind,
            evidence_location,
            _safe_graph_text(evidence, sensitive_literals)[:GRAPH.MAX_STRING_LENGTH],
            confidence, "builtin", documents[evidence_location][2],
        )
        edges.append(edge)
        adjacency.setdefault(edge.source, []).append((edge.target, edge.id))

    raw_paths = []
    start_ids = sorted(location_ids[location] for location in seed_locations if location in location_ids)
    path_limit_reached = limits.max_paths == 0 and bool(start_ids)
    for start_id in start_ids:
        if path_limit_reached:
            exhausted = True
            break
        stack = [(start_id, (start_id,), ())]
        while stack:
            if expired():
                exhausted = True
                stack.clear()
                break
            current, path_nodes, path_edges = stack.pop()
            if path_edges:
                raw_paths.append((path_nodes, path_edges))
                if len(raw_paths) >= limits.max_paths:
                    exhausted = True
                    path_limit_reached = True
                    stack.clear()
                    break
            if len(path_edges) >= 6:
                continue
            for target, edge_id in reversed(adjacency.get(current, ())):
                if target not in path_nodes:
                    stack.append((target, path_nodes + (target,), path_edges + (edge_id,)))
        if path_limit_reached:
            break

    if expired():
        return deadline_result(nodes, edges)

    unique_paths = sorted(set(raw_paths), key=lambda item: _path_sort_key(item, node_risks))
    if len(unique_paths) > limits.max_paths:
        exhausted = True
    unique_paths = unique_paths[:limits.max_paths]
    paths = []
    for index, (path_nodes, path_edges) in enumerate(unique_paths, start=1):
        domains = {
            domain for node_id in path_nodes for domain in node_risks[node_id]
        }
        ordered_domains = tuple(sorted(domains, key=lambda item: (_RISK_RANK[item], item)))
        paths.append(GraphPath(f"PATH-{index:03d}", path_nodes, path_edges, len(path_edges), ordered_domains))

    frontier_items = []
    for location in error_locations:
        node_id = error_node_ids.get(location)
        if node_id is not None and len(frontier_items) < GRAPH.MAX_FRONTIER:
            display = "repository root" if location == "." else location
            frontier_items.append(FrontierEntry(
                f"FRONTIER-{len(frontier_items) + 1:03d}", node_id,
                f"unreadable directory: {display}", ("functionality",),
            ))
    omitted_errors = len(all_error_locations) - len(error_node_ids)
    if omitted_errors and nodes and len(frontier_items) < GRAPH.MAX_FRONTIER:
        frontier_items.append(FrontierEntry(
            f"FRONTIER-{len(frontier_items) + 1:03d}", nodes[0].id,
            f"{omitted_errors} unreadable directories omitted from node capacity",
            nodes[0].risk_domains,
        ))
    if unreadable_sources and nodes and len(frontier_items) < GRAPH.MAX_FRONTIER:
        display = unreadable_sources[0]
        suffix = (
            f" and {len(unreadable_sources) - 1} more"
            if len(unreadable_sources) > 1 else ""
        )
        frontier_items.append(FrontierEntry(
            f"FRONTIER-{len(frontier_items) + 1:03d}", nodes[0].id,
            f"unreadable source: {display}{suffix}", nodes[0].risk_domains,
        ))
    if exhausted and nodes and len(frontier_items) < GRAPH.MAX_FRONTIER:
        frontier_items.append(FrontierEntry(
            f"FRONTIER-{len(frontier_items) + 1:03d}", nodes[-1].id,
            "built-in scan budget exhausted", nodes[-1].risk_domains,
        ))
    frontier = tuple(frontier_items)
    status = (
        "provider_limited" if traversal_errors or unreadable_sources else
        "budget_exhausted" if exhausted else "closed"
    )
    return BuiltInScanResult(
        tuple(nodes), tuple(edges), tuple(paths), frontier,
        {location: documents[location][2] for location in sorted(documents)},
        {path: skipped[path] for path in sorted(skipped)},
        files_scanned, bytes_scanned,
        status,
    )
