# coding:utf8

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Tuple

from .ledger import SUPPORT_LABELS


@dataclass
class RubricDimension:
    dimension_id: str
    description: str
    keywords: List[str] = field(default_factory=list)
    required: bool = True
    prefers_web: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _lower(value: Any) -> str:
    return str(value or "").lower()


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle.lower() in text for needle in needles)


def _is_complex_report_goal(goal: str) -> bool:
    text = _lower(goal)
    return _contains_any(text, [
        "report", "market", "analysis", "competitor", "competitive",
        "vendor", "product", "strategy", "recommendation", "technology",
        "报告", "市场", "分析", "竞品", "竞争", "厂商", "产品", "策略", "建议", "技术",
    ])


def build_rubric_for_goal(goal: str) -> List[RubricDimension]:
    """Infer a lightweight evidence rubric from the current search goal.

    This is deliberately deterministic. It gives the controller an auditable
    search-stop signal without spending another LLM call.
    """
    text = _lower(goal)
    dims: List[RubricDimension] = []

    def add(dimension_id, description, keywords, required=True, prefers_web=False):
        if any(dim.dimension_id == dimension_id for dim in dims):
            return
        dims.append(RubricDimension(
            dimension_id=dimension_id,
            description=description,
            keywords=keywords,
            required=required,
            prefers_web=prefers_web,
        ))

    add("core_topic", "Core topic evidence", _topic_keywords(goal), required=True)

    if _contains_any(text, ["concept", "definition", "technology", "technical", "architecture", "capability", "metric", "技术", "概念", "定义", "架构", "能力", "指标"]):
        add("technology_definition", "Technical definition, architecture, capability, or metric evidence", [
            "concept", "definition", "architecture", "capability", "metric",
            "technology", "技术", "概念", "定义", "架构", "能力", "指标",
        ])

    if _contains_any(text, ["application", "scenario", "use case", "deployment", "应用", "场景", "落地", "部署"]):
        add("application_scenarios", "Application scenario or deployment evidence", [
            "application", "scenario", "use case", "deployment",
            "应用", "场景", "落地", "部署",
        ])

    if _contains_any(text, ["competitor", "competitive", "vendor", "product comparison", "alternative", "竞品", "竞争", "厂商", "对比", "产品"]):
        add("competitors", "Competitor, vendor, or product comparison evidence", [
            "competitor", "competitive", "vendor", "comparison", "product",
            "竞品", "竞争", "厂商", "对比", "产品",
        ], prefers_web=True)

    if _contains_any(text, ["market", "business", "opportunity", "trend", "scale", "growth", "commercial", "市场", "商业", "机会", "趋势", "规模", "增长"]):
        add("market_context", "Market size, trend, business opportunity, or commercial evidence", [
            "market", "business", "opportunity", "trend", "scale", "growth",
            "commercial", "市场", "商业", "机会", "趋势", "规模", "增长",
        ], prefers_web=True)

    if _contains_any(text, ["challenge", "risk", "barrier", "limitation", "difficulty", "pain point", "挑战", "风险", "障碍", "难点", "痛点"]):
        add("challenges", "Challenge, risk, limitation, or barrier evidence", [
            "challenge", "risk", "barrier", "limitation", "difficulty",
            "挑战", "风险", "障碍", "难点", "痛点",
        ])

    if _contains_any(text, ["strategy", "recommend", "suggest", "zte", "中兴", "策略", "建议"]):
        add("strategy_recommendation", "Strategy recommendation or ZTE-specific evidence", [
            "strategy", "recommend", "suggest", "zte",
            "策略", "建议", "中兴",
        ])

    if _contains_any(text, ["latest", "recent", "2025", "2026", "current", "news", "最新", "近期", "公开", "网络"]):
        add("recent_external_context", "Recent public-web evidence for time-sensitive facts", [
            "latest", "recent", "2025", "2026", "current", "news",
            "最新", "近期", "公开", "网络",
        ], prefers_web=True)

    if len(dims) == 1 and _is_complex_report_goal(goal):
        add("technology_definition", "Technical definition or capability evidence", [
            "technology", "architecture", "capability", "技术", "架构", "能力",
        ])
        add("application_scenarios", "Application scenario evidence", [
            "application", "scenario", "use case", "应用", "场景",
        ], required=False)

    return dims


def _topic_keywords(goal: str) -> List[str]:
    words = []
    text = str(goal or "")
    for term in re.findall(r"\b[A-Za-z][A-Za-z0-9_\-]{1,}\b", text):
        lowered = term.lower()
        if lowered not in {
            "the", "and", "for", "with", "from", "report", "analysis",
            "market", "technology", "please", "about", "including",
        }:
            words.append(term)
    for term in re.findall(r"\b[A-Z]{2,8}\b", text):
        words.append(term)
    for span in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        # Keep longer named entities and a few compact phrases from the goal.
        words.append(span[:12])
        if len(span) > 12:
            words.append(span[-12:])
    deduped = []
    seen = set()
    for word in words:
        key = word.lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(word)
    return deduped[:12]


def _page_text(page: Dict[str, Any]) -> str:
    evidence = page.get("evidence") or {}
    return "\n".join([
        str(page.get("title", "")),
        str(page.get("summary", "")),
        str(evidence.get("chunk_text", "")),
        " ".join(str(x) for x in evidence.get("supported_facts", []) or []),
    ]).lower()


def _evidence_supported(page: Dict[str, Any], min_score: float) -> bool:
    evidence = page.get("evidence") or {}
    label = evidence.get("verify_label")
    score = evidence.get("verify_score", 0.0)
    try:
        score = float(score)
    except Exception:
        score = 0.0
    if label in SUPPORT_LABELS:
        return True
    return label == "background" and score >= min_score


def evaluate_rubric_gap(
    goal: str,
    pages: List[Dict[str, Any]],
    min_dimension_score: float = 0.42,
    min_supported_pages: int = 2,
) -> Dict[str, Any]:
    rubric = build_rubric_for_goal(goal)
    supported_pages = [
        page for page in pages
        if _evidence_supported(page, min_dimension_score)
    ]

    dimension_results = []
    covered_required = 0
    total_required = 0
    preferred_web_missing = []

    for dim in rubric:
        total_required += 1 if dim.required else 0
        matched_pages = []
        for page in supported_pages:
            text = _page_text(page)
            if dim.dimension_id == "core_topic":
                matched = not dim.keywords or _contains_any(text, dim.keywords)
            else:
                matched = _contains_any(text, dim.keywords)
            if matched:
                matched_pages.append(page)

        page_count = len(matched_pages)
        required_pages = 1 if dim.dimension_id == "core_topic" else min_supported_pages
        score = min(1.0, page_count / max(1, required_pages))
        covered = score >= 1.0 or (not dim.required and score > 0.0)
        if dim.required and covered:
            covered_required += 1
        if dim.prefers_web and not any((p.get("evidence") or {}).get("source_type") == "web" for p in matched_pages):
            preferred_web_missing.append(dim.dimension_id)

        dimension_results.append({
            "dimension_id": dim.dimension_id,
            "description": dim.description,
            "required": dim.required,
            "prefers_web": dim.prefers_web,
            "keywords": dim.keywords,
            "covered": covered,
            "score": round(score, 4),
            "evidence_ids": [
                (page.get("evidence") or {}).get("evidence_id")
                for page in matched_pages
                if (page.get("evidence") or {}).get("evidence_id")
            ],
        })

    required_coverage = (
        covered_required / total_required if total_required else 1.0
    )
    missing_required = [
        item["dimension_id"]
        for item in dimension_results
        if item["required"] and not item["covered"]
    ]

    should_supplement_web = bool(missing_required or preferred_web_missing)
    return {
        "rubric": [dim.to_dict() for dim in rubric],
        "dimensions": dimension_results,
        "required_coverage": round(required_coverage, 4),
        "supported_pages": len(supported_pages),
        "missing_required": missing_required,
        "preferred_web_missing": preferred_web_missing,
        "should_supplement_web": should_supplement_web,
    }
