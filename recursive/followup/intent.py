# coding:utf8

import re
from typing import Any, Dict, List


SEARCH_HINTS = (
    "market", "competitor", "vendor", "latest", "recent", "news", "benchmark",
    "case", "public", "市场", "竞品", "竞争", "厂商", "最新", "近期", "新闻",
    "对标", "案例", "公开",
)
TABLE_HINTS = ("table", "matrix", "表格", "矩阵", "对比表")
STYLE_HINTS = (
    "tone", "style", "polish", "formal", "professional", "润色", "语气",
    "正式", "专业", "表达", "措辞",
)
COMPRESS_HINTS = ("shorten", "compress", "concise", "summary", "缩短", "压缩", "精简", "摘要")
EXPAND_HINTS = ("expand", "detail", "more", "补充", "扩写", "详细", "增加")
REMOVE_HINTS = ("remove", "delete", "drop", "删掉", "删除", "去掉", "移除")
VERIFY_HINTS = ("verify", "evidence", "citation", "source", "核实", "证据", "引用", "来源")
HIGH_RISK_HINTS = (
    "roi", "cost", "budget", "market size", "cve", "0day", "zero-day",
    "成本", "投入", "预算", "市场规模", "漏洞", "零日",
)


def classify_followup_intent(instruction: str) -> Dict[str, Any]:
    """Classify a post-generation follow-up edit request."""
    text = str(instruction or "").strip()
    lowered = text.lower()
    target_hint = _extract_target_section_hint(text)

    intent_type = "section_edit"
    if _has_any(lowered, text, TABLE_HINTS):
        intent_type = "add_table"
    elif _has_any(lowered, text, REMOVE_HINTS) and _has_any(lowered, text, HIGH_RISK_HINTS):
        intent_type = "remove_unsupported"
    elif _has_any(lowered, text, VERIFY_HINTS):
        intent_type = "verify_or_cite"
    elif _has_any(lowered, text, COMPRESS_HINTS):
        intent_type = "compress"
    elif _has_any(lowered, text, EXPAND_HINTS):
        intent_type = "expand"
    elif _has_any(lowered, text, STYLE_HINTS):
        intent_type = "style"

    requires_search_repair = bool(
        intent_type in ("add_table", "expand")
        and _has_any(lowered, text, SEARCH_HINTS)
    )
    if _has_any(lowered, text, ("补充资料", "补检索", "重新检索", "search", "retrieve")):
        requires_search_repair = True

    scope = "section" if target_hint else "auto"
    if intent_type in ("style", "compress") and not target_hint:
        scope = "full_report"
    if intent_type in ("remove_unsupported", "verify_or_cite") and not target_hint:
        scope = "evidence_sensitive"

    return {
        "version": "1.0",
        "instruction": text,
        "intent_type": intent_type,
        "target_section_hint": target_hint,
        "scope": scope,
        "requires_search_repair": requires_search_repair,
        "risk_level": "high" if _has_any(lowered, text, HIGH_RISK_HINTS) else "medium",
        "keywords": _matched_keywords(lowered, text),
    }


def _extract_target_section_hint(text: str) -> str:
    patterns = [
        r"[“\"']([^“”\"']{2,40})[”\"']",
        r"(?:polish|rewrite|revise|edit|update|expand|shorten|compress|improve)\s+(?:the\s+)?([A-Z][A-Za-z0-9 /\-]{2,50})(?:\s+section|\s+chapter|[.。]|$)",
        r"(?:把|将|修改|改写|重写|补充|完善)\s*([^\s，。,.]{2,30}(?:章节|部分|分析|建议|路线图|对比|摘要))",
        r"(第[一二三四五六七八九十\d]+[章节部分])",
        r"(\d+(?:\.\d+)*\s*[^\s，。,.]{2,30})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def _has_any(lowered: str, original: str, hints) -> bool:
    for hint in hints:
        key = str(hint)
        haystack = original if re.search(r"[\u4e00-\u9fff]", key) else lowered
        needle = key if re.search(r"[\u4e00-\u9fff]", key) else key.lower()
        if needle in haystack:
            return True
    return False


def _matched_keywords(lowered: str, original: str) -> List[str]:
    matched = []
    for hints in (
        SEARCH_HINTS,
        TABLE_HINTS,
        STYLE_HINTS,
        COMPRESS_HINTS,
        EXPAND_HINTS,
        REMOVE_HINTS,
        VERIFY_HINTS,
        HIGH_RISK_HINTS,
    ):
        for hint in hints:
            key = str(hint)
            haystack = original if re.search(r"[\u4e00-\u9fff]", key) else lowered
            needle = key if re.search(r"[\u4e00-\u9fff]", key) else key.lower()
            if needle in haystack and key not in matched:
                matched.append(key)
    return matched[:12]
