"""Mechanical scorer for the Claude Code v0.5 smoke batch.

Reuses the harness's deterministic contracts: negative cases must not emit
refinement IDs or report workflow markers; positive cases are checked for a
canonical report validated by the shipped validator. Topic coverage for
must_detect entries is recorded as informational keyword hits only — it is
NOT an adjudication and never counts toward the mechanical verdict.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

_REFINEMENT_ID = re.compile(r"\b(?:RPT|REQ|IMP|INV|DEC|AC)-\d{3}\b")
_REPORT_WORKFLOW = re.compile(
    r"(?:^|\n)\s*#{1,6}\s+(?:requirements impact report|impact ledger|planning handoff)\b"
    r"|\b(?:begin|start|activate|perform)\s+(?:the\s+)?impact refinement\b",
    re.IGNORECASE,
)

_TOPIC_KEYWORDS = {
    "owner/admin distinction": ("owner", "admin"),
    "invitation scope": ("invitation", "invit"),
    "audit behavior": ("audit",),
    "RESTRICT constraint": ("restrict",),
    "retention window": ("retention",),
    "worker path": ("worker",),
    "iOS decoding": ("ios", "decod"),
    "cached payloads": ("cache",),
    "deprecation promise": ("deprecat",),
    "tenant isolation": ("tenant",),
    "role invalidation": ("role", "invalidat"),
    "event staleness": ("event", "stale"),
    "idempotency": ("idempot",),
    "status rendering": ("status",),
    "timeout after capture": ("timeout", "capture"),
    "expiry invariant": ("expir",),
    "revocation path": ("revo",),
    "key rotation": ("rotat",),
    "timestamp conflict": ("timestamp", "updated_at"),
    "tombstone window": ("tombstone",),
    "ordering limits": ("order",),
    "object overwrite": ("object", "overwrit", "deterministic"),
    "retry bound change": ("retry", "five", "bound"),
    "dead letter consumers": ("dead", "letter", "dead_letter"),
}


def load_validator():
    path = (
        ROOT / "skills" / "requirements-impact-refiner" / "scripts"
        / "validate-impact-report.py"
    )
    spec = importlib.util.spec_from_file_location("_smoke_validator", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def extract_report(output: str):
    marker = "# Requirements Impact Report"
    index = output.find(marker)
    if index < 0:
        return None
    return output[index:]


def topic_hits(output: str, topics):
    lowered = output.lower()
    hits = {}
    for topic in topics:
        keywords = _TOPIC_KEYWORDS.get(topic, tuple(topic.lower().split()))
        hits[topic] = any(keyword.lower() in lowered for keyword in keywords)
    return hits


def main():
    validator = load_validator()
    cases = {
        case["id"]: case
        for case in json.loads((ROOT / "evals" / "cases.json").read_text())["cases"]
    }
    rows = []
    for case_dir in sorted((HERE / "raw").iterdir()):
        if not case_dir.is_dir():
            continue
        case = cases[case_dir.name]
        output = (case_dir / "final.md").read_text()
        if case["kind"] == "negative":
            ids = sorted(set(_REFINEMENT_ID.findall(output)))
            workflow = _REPORT_WORKFLOW.search(output) is not None
            verdict = "pass" if not ids and not workflow else "fail"
            detail = {"refinement_ids": ids, "report_workflow": workflow}
        else:
            report = extract_report(output)
            if report is None:
                verdict = "fail"
                detail = {"report": "absent"}
            else:
                errors = validator.validate_report(report)
                verdict = "pass" if not errors else "fail"
                detail = {"report": "present", "validator_errors": errors[:8]}
            detail["topic_hits_informational"] = topic_hits(
                output, case["must_detect"]
            )
        rows.append({"case": case_dir.name, "kind": case["kind"],
                     "mechanical": verdict, "detail": detail})
    (HERE / "scores.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    )
    passes = sum(1 for row in rows if row["mechanical"] == "pass")
    print(f"mechanical: {passes}/{len(rows)}")
    for row in rows:
        print(f"  {row['mechanical']:4s} {row['kind']:9s} {row['case']}")


if __name__ == "__main__":
    main()
