"""Bounded user-facing rendering for Fast Scan receipts."""
from typing import Mapping
WORD_LIMIT = 180
AUDIENCES = {"simple", "balanced", "technical"}

def _text(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("\n", " "))

def _bounded(body, footer):
    words, footer_words = body.split(), footer.split()
    available = max(0, WORD_LIMIT - len(footer_words))
    if len(words) > available: words = words[:max(0, available - 1)] + ["…"]
    return " ".join(words + footer_words)

def render_fast_scan(receipt: Mapping[str, object], audience: str) -> str:
    if audience not in AUDIENCES: raise ValueError("audience is invalid")
    status = receipt.get("status")
    footer = f"Coverage: {status}; {receipt.get('elapsed_ms', 0)} ms; cache {receipt.get('cache_status', 'bypassed')}."
    if status != "needs_input":
        footer += " Do you want detailed refinement?"
    else:
        footer += (
            " Which file, symbol, or API is the concrete boundary of this"
            " change?"
        )
    if status == "needs_input":
        candidates = receipt.get("candidates", [])
        listed = "; ".join(_text(row.get("term")) + (" (" + _text(row.get("location")) + ")" if row.get("location") else "") for row in candidates[:3]) or "no repository-backed candidate"
        return _bounded("Fast impact scan needs more input. Candidate boundaries: " + listed + ".", footer)
    graph = receipt.get("graph_receipt", {})
    nodes = {row.get("id"): row for row in graph.get("nodes", [])}
    edges = {row.get("id"): row for row in graph.get("edges", [])}
    lines = ["Fast impact scan: " + str(receipt.get("risk_level", "unknown")) + " risk.", "Possible issue paths:"]
    for path in graph.get("paths", [])[:8]:
        path_nodes = [nodes.get(key, {}) for key in path.get("nodes", [])]
        labels = " → ".join(_text(row.get("label", key)) for row, key in zip(path_nodes, path.get("nodes", [])))
        line = "- " + labels + ": " + _text(", ".join(path.get("risk_domains", [])) or "unknown risk") + "."
        if audience == "technical":
            path_edges = [edges.get(key, {}) for key in path.get("edges", [])]
            providers = sorted({row.get("provider") for row in path_nodes if row.get("provider")})
            confidences = sorted({row.get("confidence") for row in path_edges + path_nodes if row.get("confidence")})
            locations = [row.get("location") for row in path_nodes if row.get("location")]
            line += " provider " + _text("+".join(providers) or "unavailable")
            line += "; confidence " + _text("+".join(confidences) or "unknown")
            line += "; location " + _text(" + ".join(locations) or "unavailable") + "."
        lines.append(line)
    frontier = receipt.get("frontier", [])
    if frontier: lines.append("Unknown frontier: " + "; ".join(_text(row.get("reason", "unknown")) for row in frontier[:3]) + ".")
    if status == "partial": lines.append("Partial result: unknown impact may remain.")
    return _bounded(" ".join(lines), footer)
