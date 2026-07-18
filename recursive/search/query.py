# coding:utf8

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence


EN_STOPWORDS = {
    "about", "above", "after", "also", "analysis", "and", "are", "based",
    "brief", "build", "case", "compare", "create", "describe", "detail",
    "explain", "find", "for", "form", "from", "give", "how", "include",
    "including", "into", "make", "market", "of", "on", "overview", "please",
    "provide", "report", "research", "search", "study", "summary", "technical",
    "technology", "the", "this", "trend", "use", "what", "with", "write",
}

CJK_STOP_FRAGMENTS = (
    "请", "进行", "形成", "分析", "报告", "介绍", "中的", "一个", "以及",
    "包括", "相关", "信息", "技术", "系统", "方案", "市场", "竞品", "趋势",
    "研究", "对比", "说明", "生成", "撰写", "基于", "知识库",
)

GAP_QUERY_TERMS = {
    "competitors": {
        "zh": ["竞品对比 厂商分析", "竞争格局 产品对比"],
        "en": ["competitor comparison vendor analysis", "competitive landscape product comparison"],
    },
    "market_context": {
        "zh": ["市场规模 趋势 2026", "商业机会 增长 预测"],
        "en": ["market size trends 2026", "business opportunity growth forecast"],
    },
    "recent_external_context": {
        "zh": ["最新进展 2026 公开资料", "近期新闻 行业动态"],
        "en": ["latest developments 2026 public sources", "recent news industry updates"],
    },
    "application_scenarios": {
        "zh": ["应用场景 落地案例 部署", "行业应用 使用场景"],
        "en": ["application scenarios deployment case studies", "industry use cases"],
    },
    "technology_definition": {
        "zh": ["技术架构 原理 能力 指标", "定义 架构 核心能力"],
        "en": ["technical architecture principles capabilities metrics", "definition architecture core capabilities"],
    },
    "challenges": {
        "zh": ["挑战 风险 难点 局限", "实施障碍 痛点"],
        "en": ["challenges risks limitations barriers", "implementation barriers pain points"],
    },
    "strategy_recommendation": {
        "zh": ["策略建议 路线图 发展方向", "实施建议 商业策略"],
        "en": ["strategy recommendations roadmap direction", "implementation recommendations business strategy"],
    },
}


def _dedupe(items: Iterable[str], limit: Optional[int] = None) -> List[str]:
    result = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def _clean_cjk_span(span: str) -> str:
    cleaned = str(span or "")
    for fragment in CJK_STOP_FRAGMENTS:
        cleaned = cleaned.replace(fragment, " ")
    return cleaned


def extract_relevance_terms(text: str, max_terms: int = 18) -> List[str]:
    """Extract cheap lexical signals for generic KB pre-ranking."""
    candidates: List[str] = []
    raw = str(text or "")

    for term in re.findall(r"\b[A-Z]{2,12}\b", raw):
        candidates.append(term)

    for term in re.findall(r"\b[A-Za-z][A-Za-z0-9_\-]{1,}\b", raw):
        lowered = term.lower()
        if lowered not in EN_STOPWORDS and len(lowered) > 1:
            candidates.append(term)

    for span in re.findall(r"[\u4e00-\u9fff]{2,}", raw):
        for part in re.findall(r"[\u4e00-\u9fff]{2,}", _clean_cjk_span(span)):
            if len(part) <= 8:
                candidates.append(part)
                continue
            candidates.append(part[:6])
            candidates.append(part[-6:])
            for size in (6, 4):
                step = max(1, size - 1)
                for idx in range(0, max(0, len(part) - size + 1), step):
                    candidates.append(part[idx:idx + size])

    return _dedupe(candidates, max_terms)


def rubric_gap_dimensions(rubric_gap: Optional[Dict[str, Any]]) -> List[str]:
    gap = rubric_gap or {}
    dims: List[str] = []
    for key in ("missing_required", "preferred_web_missing"):
        value = gap.get(key, []) or []
        if isinstance(value, str):
            value = [value]
        dims.extend(str(item) for item in value if item)
    return _dedupe(dims)


def build_rubric_gap_queries(
    core: str,
    language: str,
    rubric_gap: Optional[Dict[str, Any]],
    max_queries: Optional[int] = None,
) -> List[str]:
    lang = "zh" if str(language or "").lower().startswith("zh") else "en"
    base = str(core or "").strip()
    if not base:
        return []

    queries = []
    for dimension_id in rubric_gap_dimensions(rubric_gap):
        terms = GAP_QUERY_TERMS.get(dimension_id, {})
        for suffix in terms.get(lang, terms.get("en", [])):
            queries.append("{} {}".format(base, suffix))

    return _dedupe(queries, max_queries)


def infer_page_source_type(
    page: Dict[str, Any],
    turn_result: Optional[Dict[str, Any]] = None,
    default: str = "web",
) -> str:
    evidence = (page or {}).get("evidence") or {}
    raw_values: Sequence[Any] = (
        evidence.get("source_type"),
        (page or {}).get("source_type"),
        (page or {}).get("source"),
        (turn_result or {}).get("source_type"),
        (turn_result or {}).get("source"),
    )
    raw = " ".join(str(value or "").lower() for value in raw_values)
    url = str((page or {}).get("url", "") or "").lower()

    if any(token in raw for token in ("local kb", "local_knowledge", "knowledge base", "chroma", "kb")):
        return "kb"
    if url.startswith(("local-kb://", "kb://", "chroma://")):
        return "kb"
    if any(token in raw for token in ("web", "serpapi", "google", "bing", "search")):
        return "web"
    if url.startswith(("http://", "https://")):
        return "web"
    return default


def source_type_label(source_type: str) -> str:
    return "Local KB" if str(source_type or "").lower() == "kb" else "Web Search"
