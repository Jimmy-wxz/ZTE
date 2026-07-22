# coding:utf8

import hashlib
import re
from typing import Any, Dict


TASK_KEYWORDS = {
    "technical_intro": (
        "what is", "definition", "overview", "architecture", "principle",
        "concept", "capability", "explain", "介绍", "定义", "概念", "原理", "架构",
    ),
    "market_competitor": (
        "market", "competitor", "competition", "vendor", "benchmark",
        "trend", "industry", "business", "commercial", "市场", "竞品", "竞争",
        "厂商", "对标", "趋势", "行业", "商业",
    ),
    "strategy_roadmap": (
        "strategy", "roadmap", "recommendation", "implementation",
        "planning", "governance", "roi", "cost", "策略", "路线图", "建议",
        "实施", "规划", "治理", "成本", "投入",
    ),
    "risk_security": (
        "risk", "security", "vulnerability", "compliance", "privacy",
        "attack", "cve", "zero-day", "0day", "风险", "安全", "漏洞", "合规",
        "隐私", "攻击",
    ),
    "research_paper": (
        "paper", "research", "method", "experiment", "baseline",
        "ablation", "innovation", "论文", "研究", "方法", "实验", "基线",
        "消融", "创新",
    ),
}

HIGH_RISK_TERMS = (
    "roi", "cost", "budget", "market size", "growth", "cagr", "forecast",
    "cve", "zero-day", "0day", "market share", "成本", "投入", "预算",
    "市场规模", "增长率", "预测", "份额", "漏洞",
)


def extract_task_features(
    prompt: str,
    config: Dict[str, Any] = None,
    engine_backend: str = "",
    item: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Extract deterministic task features for policy decisions."""
    config = config or {}
    item = item or {}
    text = str(prompt or "")
    lowered = text.lower()
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]*", text)
    numbers = re.findall(r"\d+(?:\.\d+)?%?", text)

    keyword_hits = {
        family: _keyword_hits(lowered, text, keywords)
        for family, keywords in TASK_KEYWORDS.items()
    }
    task_family = _select_task_family(keyword_hits, len(text))
    requirement_count = _requirement_count(text)
    complexity_score = _complexity_score(
        char_count=len(text),
        requirement_count=requirement_count,
        numbers_count=len(numbers),
        keyword_hits=keyword_hits,
    )

    return {
        "version": "1.0",
        "prompt_hash": hashlib.sha1(
            text.encode("utf-8", errors="ignore")).hexdigest()[:16],
        "task_id": item.get("id", ""),
        "language": "zh" if cjk_chars >= 5 else "en",
        "char_count": len(text),
        "word_count": len(words),
        "cjk_char_count": cjk_chars,
        "number_count": len(numbers),
        "requirement_count": requirement_count,
        "task_family": task_family,
        "keyword_hits": keyword_hits,
        "high_risk_term_count": _count_terms(lowered, text, HIGH_RISK_TERMS),
        "complexity_score": complexity_score,
        "engine_backend": str(engine_backend or ""),
        "config_language": config.get("language", ""),
        "uses_kb": _env_like_enabled("WRITEHERE_USE_KB"),
        "kb_name": _env_value("WRITEHERE_KB_NAME"),
    }


def _keyword_hits(lowered: str, original: str, keywords) -> int:
    count = 0
    for keyword in keywords:
        key = str(keyword)
        haystack = original if re.search(r"[\u4e00-\u9fff]", key) else lowered
        needle = key if re.search(r"[\u4e00-\u9fff]", key) else key.lower()
        if needle in haystack:
            count += 1
    return count


def _select_task_family(keyword_hits: Dict[str, int], char_count: int) -> str:
    if not keyword_hits:
        return "general_report"
    ordered = sorted(keyword_hits.items(), key=lambda item: (-item[1], item[0]))
    if ordered[0][1] <= 0:
        return "technical_intro" if char_count <= 120 else "general_report"
    return ordered[0][0]


def _requirement_count(text: str) -> int:
    separators = re.findall(
        r"[,;，；、\n]| and | with | including | include | 包括|以及|并且|同时",
        str(text or "").lower(),
    )
    return len(separators)


def _complexity_score(
    char_count: int,
    requirement_count: int,
    numbers_count: int,
    keyword_hits: Dict[str, int],
) -> float:
    score = 0.0
    if char_count > 100:
        score += 0.2
    if char_count > 220:
        score += 0.2
    score += min(0.25, requirement_count * 0.05)
    score += min(0.15, numbers_count * 0.03)
    score += min(0.25, (
        keyword_hits.get("market_competitor", 0)
        + keyword_hits.get("strategy_roadmap", 0)
        + keyword_hits.get("risk_security", 0)
        + keyword_hits.get("research_paper", 0)
    ) * 0.04)
    return round(min(1.0, score), 4)


def _count_terms(lowered: str, original: str, terms) -> int:
    count = 0
    for term in terms:
        key = str(term)
        haystack = original if re.search(r"[\u4e00-\u9fff]", key) else lowered
        needle = key if re.search(r"[\u4e00-\u9fff]", key) else key.lower()
        if needle in haystack:
            count += 1
    return count


def _env_value(name: str) -> str:
    try:
        import os

        return os.environ.get(name, "")
    except Exception:
        return ""


def _env_like_enabled(name: str) -> bool:
    value = _env_value(name)
    return str(value).strip().lower() in ("1", "true", "yes", "on")
