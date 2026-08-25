"""Bounded user-facing rendering for Fast Scan receipts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import TypeGuard

WORD_LIMIT = 180
AUDIENCES = {"simple", "balanced", "technical"}
LOCALES = {"en", "ko", "ja"}

RISK_LABELS = {
    "ko": {
        "critical": "치명적",
        "high": "높음",
        "medium": "중간",
        "low": "낮음",
        "unknown": "미확인",
    },
    "ja": {"critical": "重大", "high": "高", "medium": "中", "low": "低", "unknown": "未確認"},
}
STATUS_LABELS = {
    "ko": {"complete": "완료", "partial": "부분", "needs_input": "추가 입력 필요"},
    "ja": {"complete": "完了", "partial": "部分", "needs_input": "追加情報が必要"},
}
DOMAIN_LABELS = {
    "ko": {
        "authorization/privacy": "권한·개인정보",
        "interfaces": "인터페이스",
        "data": "데이터",
        "state/concurrency": "상태·동시성",
        "operations": "운영",
        "compatibility": "호환성",
        "regression": "회귀",
        "functionality": "기능",
        "legal/policy": "법률·정책",
    },
    "ja": {
        "authorization/privacy": "認可・プライバシー",
        "interfaces": "インターフェース",
        "data": "データ",
        "state/concurrency": "状態・並行性",
        "operations": "運用",
        "compatibility": "互換性",
        "regression": "回帰",
        "functionality": "機能",
        "legal/policy": "法務・ポリシー",
    },
}

FRONTIER_PREFIXES = {
    "ko": (
        (
            "provider unavailable; built-in fallback used: ",
            "선택 분석 도구를 사용할 수 없어 내장 분석을 사용함: ",
        ),
        ("source inventory incomplete: ", "소스 목록이 불완전함: "),
    ),
    "ja": (
        (
            "provider unavailable; built-in fallback used: ",
            "選択した分析ツールを利用できないため内蔵分析を使用: ",
        ),
        ("source inventory incomplete: ", "ソース一覧が不完全: "),
    ),
}
FRONTIER_EXACT = {
    "ko": {
        "built-in scan path capacity exhausted": "내장 분석의 경로 개수 한도에 도달함",
        "built-in scan resource capacity exhausted": "내장 분석의 자원 한도에 도달함",
        "built-in scan deadline exhausted": "내장 분석의 시간 한도에 도달함",
        "graph coverage remains incomplete": "그래프 확인 범위가 아직 불완전함",
    },
    "ja": {
        "built-in scan path capacity exhausted": "内蔵分析の経路数上限に到達",
        "built-in scan resource capacity exhausted": "内蔵分析のリソース上限に到達",
        "built-in scan deadline exhausted": "内蔵分析の時間上限に到達",
        "graph coverage remains incomplete": "グラフの確認範囲がまだ不完全",
    },
}


def _text(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "&#124;")
        .replace("\n", " ")
    )


def _mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping) and all(isinstance(key, str) for key in value)


def _rows(value: object) -> TypeGuard[Sequence[Mapping[str, object]]]:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and all(_mapping(row) for row in value)
    )


def _values(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _strings(value: object) -> TypeGuard[Sequence[str]]:
    return _values(value) and all(isinstance(item, str) for item in value)


def _localized(value, locale, table):
    return table.get(locale, {}).get(value, value)


def _domains(values, locale):
    labels = [_localized(value, locale, DOMAIN_LABELS) for value in values]
    if labels:
        return ", ".join(labels)
    return {"ko": "미확인 위험", "ja": "未確認のリスク"}.get(locale, "unknown risk")


def _frontier_reason(reason, locale):
    reason = str(reason or "unknown")
    exact = FRONTIER_EXACT.get(locale, {}).get(reason)
    if exact:
        return exact
    for prefix, translated in FRONTIER_PREFIXES.get(locale, ()):
        if reason.startswith(prefix):
            return translated + reason[len(prefix) :]
    return reason


def _bounded_lines(lines, footer, protected=""):
    """Assemble whole body lines under the word cap. The footer always
    survives; protected safety text is word-trimmed only if it alone would
    overflow; body lines are dropped whole, never cut mid-line, so technical
    provenance stays intact."""
    footer_words = footer.split()
    protected_words = protected.split()
    safety_budget = max(0, WORD_LIMIT - len(footer_words))
    if len(protected_words) > safety_budget:
        protected_words = [*protected_words[: max(0, safety_budget - 1)], "…"]
    available = max(0, WORD_LIMIT - len(footer_words) - len(protected_words))
    kept_lines = []
    used = 0
    for line in lines:
        line_words = line.split()
        if used + len(line_words) > available:
            if available > 0:
                if used < available:
                    kept_lines.append(["…"])
                elif kept_lines:
                    # Replacing the last complete line preserves the
                    # no-mid-line provenance guarantee and budgets the marker.
                    kept_lines[-1] = ["…"]
            break
        kept_lines.append(line_words)
        used += len(line_words)
    kept = [word for line in kept_lines for word in line]
    return " ".join(kept + protected_words + footer_words)


def render_fast_scan(receipt: Mapping[str, object], audience: str, locale: str = "en") -> str:
    if audience not in AUDIENCES:
        raise ValueError("audience is invalid")
    if locale not in LOCALES:
        locale = "en"
    status = str(receipt.get("status", "needs_input"))
    status_label = _localized(status, locale, STATUS_LABELS)
    cache = str(receipt.get("cache_status", "bypassed"))
    if locale == "ko":
        cache_label = {"hit": "적중", "miss": "미적중", "bypassed": "사용 안 함"}.get(cache, cache)
        footer = f"검사 범위: {status_label}; {receipt.get('elapsed_ms', 0)}ms; 캐시 {cache_label}."
    elif locale == "ja":
        cache_label = {"hit": "ヒット", "miss": "ミス", "bypassed": "未使用"}.get(cache, cache)
        footer = (
            f"確認範囲: {status_label}; {receipt.get('elapsed_ms', 0)}ms; キャッシュ {cache_label}."
        )
    else:
        footer = f"Coverage: {status}; {receipt.get('elapsed_ms', 0)} ms; cache {cache}."
    if status != "needs_input":
        footer += {
            "ko": " 상세 영향도 정제를 진행할까요?",
            "ja": " 詳細な影響分析を続けますか?",
        }.get(locale, " Do you want detailed refinement?")
    else:
        footer += {
            "ko": " 변경 범위가 되는 구체적인 파일, 심볼 또는 API는 무엇인가요?",
            "ja": " 変更境界となる具体的なファイル、シンボル、または API は何ですか?",
        }.get(locale, " Which file, symbol, or API is the concrete boundary of this change?")
    if status == "needs_input":
        candidate_value = receipt.get("candidates", [])
        candidates = candidate_value if _rows(candidate_value) else ()
        empty = {"ko": "저장소에서 확인된 후보 없음", "ja": "リポジトリで確認できた候補なし"}.get(
            locale, "no repository-backed candidate"
        )
        listed = (
            "; ".join(
                _text(row.get("term"))
                + (" (" + _text(row.get("location")) + ")" if row.get("location") else "")
                for row in candidates[:3]
            )
            or empty
        )
        intro = {
            "ko": "빠른 영향도 검사에 추가 입력이 필요합니다. 후보 범위: ",
            "ja": "高速影響スキャンには追加情報が必要です。候補範囲: ",
        }.get(locale, "Fast impact scan needs more input. Candidate boundaries: ")
        return _bounded_lines([intro + listed + "."], footer)
    graph_value = receipt.get("graph_receipt", {})
    graph = graph_value if _mapping(graph_value) else {}
    node_value = graph.get("nodes", [])
    node_rows = node_value if _rows(node_value) else ()
    nodes = {row.get("id"): row for row in node_rows}
    label_counts = Counter(str(row.get("label")) for row in node_rows)
    edge_value = graph.get("edges", [])
    edge_rows = edge_value if _rows(edge_value) else ()
    edges = {row.get("id"): row for row in edge_rows}
    risk = _localized(receipt.get("risk_level", "unknown"), locale, RISK_LABELS)
    if locale == "ko":
        lines = [f"빠른 영향도 검사: 위험도 {risk}.", "발생 가능한 영향 경로:"]
    elif locale == "ja":
        lines = [f"高速影響スキャン: リスク {risk}。", "発生する可能性のある影響経路:"]
    else:
        lines = ["Fast impact scan: " + str(risk) + " risk.", "Possible issue paths:"]
    path_value = graph.get("paths", [])
    path_rows = path_value if _rows(path_value) else ()
    for path in path_rows[:8]:
        path_node_value = path.get("nodes", [])
        path_node_ids = path_node_value if _strings(path_node_value) else ()
        path_nodes = [nodes.get(key, {}) for key in path_node_ids]
        display_labels = []
        for row, key in zip(path_nodes, path_node_ids):
            label = str(row.get("label", key))
            location = row.get("location")
            display_labels.append(location if location and label_counts[label] > 1 else label)
        labels = " → ".join(_text(value) for value in display_labels)
        domain_value = path.get("risk_domains", [])
        domains = domain_value if _values(domain_value) else ()
        line = "- " + labels + ": " + _text(_domains(domains, locale)) + "."
        if audience == "technical":
            path_edge_value = path.get("edges", [])
            path_edge_ids = path_edge_value if _strings(path_edge_value) else ()
            path_edges = [edges.get(key, {}) for key in path_edge_ids]
            providers = sorted(
                {str(row.get("provider")) for row in path_nodes if row.get("provider")}
            )
            confidences = sorted(
                {
                    str(row.get("confidence"))
                    for row in path_edges + path_nodes
                    if row.get("confidence")
                }
            )
            locations = [str(row.get("location")) for row in path_nodes if row.get("location")]
            keys = {
                "ko": (" 제공자 ", "; 신뢰도 ", "; 위치 ", "사용 불가", "미확인"),
                "ja": (" provider ", "; 信頼度 ", "; 場所 ", "利用不可", "未確認"),
            }.get(locale, (" provider ", "; confidence ", "; location ", "unavailable", "unknown"))
            line += keys[0] + _text("+".join(providers) or keys[3])
            line += keys[1] + _text("+".join(confidences) or keys[4])
            line += keys[2] + _text(" + ".join(locations) or keys[3]) + "."
        lines.append(line)
    frontier_value = receipt.get("frontier", [])
    frontier = frontier_value if _rows(frontier_value) else ()
    protected = []
    if status == "partial":
        protected.append(
            {
                "ko": "부분 결과: 아직 확인되지 않은 영향이 남아 있을 수 있습니다.",
                "ja": "部分的な結果: 未確認の影響が残っている可能性があります。",
            }.get(locale, "Partial result: unknown impact may remain.")
        )
    if frontier:
        heading = {"ko": "미확인 범위: ", "ja": "未確認の範囲: "}.get(locale, "Unknown frontier: ")
        protected.append(
            heading
            + "; ".join(_text(_frontier_reason(row.get("reason"), locale)) for row in frontier[:3])
            + "."
        )
    return _bounded_lines(lines, footer, " ".join(protected))
