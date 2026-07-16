# coding:utf8

import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Optional


VALID_SEARCH_MODES = {"atom", "wide", "deep"}

ENV_OVERRIDE_KEYS = {
    "kb_variant_topk": "WRITEHERE_KB_VARIANT_TOPK",
    "kb_rerank_candidate_limit": "WRITEHERE_KB_RERANK_CANDIDATES",
    "kb_rerank_cpu_candidates": "WRITEHERE_KB_RERANK_CPU_CANDIDATES",
    "kb_rerank_mode": "WRITEHERE_KB_RERANK_MODE",
    "kb_final_topk": "WRITEHERE_KB_FINAL_TOPK",
    "max_search_queries": "WRITEHERE_MAX_SEARCH_QUERIES",
    "execute_retry_limit": "WRITEHERE_RETRY_LIMIT",
    "merge_retry_limit": "WRITEHERE_RETRY_LIMIT",
    "search_parse_retry_limit": "WRITEHERE_RETRY_LIMIT",
}


MODE_SETTINGS = {
    "atom": {
        "kb_variant_topk": 3,
        "kb_rerank_candidate_limit": 12,
        "kb_rerank_cpu_candidates": 6,
        "kb_rerank_mode": "fast",
        "kb_final_topk": 4,
        "kb_web_fallback_coverage_threshold": 0.50,
        "max_search_queries": 2,
        "topk": 8,
        "pk_quota": 6,
        "select_quota": 4,
        "search_max_thread": 2,
        "webpage_helper_max_threads": 6,
        "merge_page_threshold": 10,
        "llm_merge": False,
        "execute_retry_limit": 1,
        "merge_retry_limit": 1,
        "search_parse_retry_limit": 1,
    },
    "wide": {
        "kb_variant_topk": 4,
        "kb_rerank_candidate_limit": 24,
        "kb_rerank_cpu_candidates": 8,
        "kb_rerank_mode": "auto",
        "kb_final_topk": 6,
        "kb_web_fallback_coverage_threshold": 0.60,
        "max_search_queries": 4,
        "topk": 12,
        "pk_quota": 12,
        "select_quota": 8,
        "search_max_thread": 4,
        "webpage_helper_max_threads": 10,
        "merge_page_threshold": 8,
        "llm_merge": "auto",
        "execute_retry_limit": 2,
        "merge_retry_limit": 2,
        "search_parse_retry_limit": 2,
    },
    "deep": {
        "kb_variant_topk": 5,
        "kb_rerank_candidate_limit": 36,
        "kb_rerank_cpu_candidates": 12,
        "kb_rerank_mode": "auto",
        "kb_final_topk": 8,
        "kb_web_fallback_coverage_threshold": 0.68,
        "kb_web_force_supplement": True,
        "max_search_queries": 6,
        "topk": 20,
        "pk_quota": 18,
        "select_quota": 10,
        "search_max_thread": 4,
        "webpage_helper_max_threads": 12,
        "merge_page_threshold": 6,
        "llm_merge": "auto",
        "execute_retry_limit": 2,
        "merge_retry_limit": 2,
        "search_parse_retry_limit": 2,
    },
}


ATOM_HINTS = (
    "what is", "define", "definition", "concept", "explain", "overview",
    "introduction", "principle", "metric", "capability", "feature",
    "是什么", "定义", "概念", "介绍", "解释", "说明", "原理", "指标", "功能",
)

WIDE_HINTS = (
    "market", "competitor", "competitive", "vendor", "product comparison",
    "comparison", "benchmark", "trend", "industry", "latest", "recent",
    "news", "public", "commercial", "business", "opportunity", "growth",
    "市场", "竞品", "竞争", "厂商", "产品对比", "对比", "趋势", "行业",
    "最新", "近期", "公开", "商业", "机会", "增长", "规模",
)

DEEP_HINTS = (
    "strategy", "roadmap", "recommendation", "architecture design",
    "solution", "implementation", "planning", "risk", "challenge",
    "trade-off", "tradeoff", "multi-agent", "recursive", "rubric",
    "auditable", "framework", "system", "research", "paper",
    "战略", "路线图", "建议", "方案", "实施", "规划", "风险", "挑战",
    "取舍", "多智能体", "递归", "框架", "系统", "论文", "研究",
)

REPORT_HINTS = (
    "report", "analysis", "brief", "study", "white paper",
    "报告", "分析", "研究", "白皮书",
)


@dataclass
class SearchModeProfile:
    mode: str
    reason: str
    settings: Dict[str, Any]
    scores: Dict[str, int]
    forced: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _lower(value: Any) -> str:
    return str(value or "").lower()


def _count_hints(text: str, hints: Iterable[str]) -> int:
    return sum(1 for hint in hints if hint.lower() in text)


def _requirement_count(text: str) -> int:
    separators = re.findall(r"[,;；，、\n]| and | with | including | 包括|以及|并|同时", text)
    return len(separators)


def _normalize_forced_mode(value: Optional[str]) -> str:
    mode = _lower(value).strip()
    if mode in VALID_SEARCH_MODES:
        return mode
    return "auto"


def classify_search_mode(
    goal: str,
    root_question: str = "",
    task_length: Optional[int] = None,
    forced_mode: Optional[str] = None,
) -> SearchModeProfile:
    forced = _normalize_forced_mode(forced_mode)
    if forced != "auto":
        return SearchModeProfile(
            mode=forced,
            reason="forced by config",
            settings=dict(MODE_SETTINGS[forced]),
            scores={"atom": 0, "wide": 0, "deep": 0},
            forced=True,
        )

    goal_text = _lower(goal)
    root_text = _lower(root_question)
    char_len = len(str(goal or ""))

    atom_score = _count_hints(goal_text, ATOM_HINTS)
    wide_score = _count_hints(goal_text, WIDE_HINTS)
    deep_score = _count_hints(goal_text, DEEP_HINTS)
    report_score = _count_hints(goal_text, REPORT_HINTS)
    root_wide_score = _count_hints(root_text, WIDE_HINTS)
    root_deep_score = _count_hints(root_text, DEEP_HINTS)

    if char_len <= 90 and wide_score == 0 and deep_score == 0:
        atom_score += 2
    if atom_score == 0 and wide_score == 0 and root_wide_score >= 2:
        wide_score += 1
    if atom_score == 0 and deep_score == 0 and root_deep_score >= 2 and char_len > 90:
        deep_score += 1
    if char_len > 160:
        deep_score += 1
    if _requirement_count(goal_text) >= 3:
        deep_score += 1
    if task_length:
        try:
            if int(task_length) >= 1000:
                deep_score += 1
        except Exception:
            pass
    if report_score and wide_score:
        wide_score += 1
    if report_score and deep_score:
        deep_score += 1
    if wide_score >= 2 and deep_score >= 2:
        deep_score += 1

    scores = {"atom": atom_score, "wide": wide_score, "deep": deep_score}
    if deep_score >= 3 and deep_score >= wide_score:
        mode = "deep"
        reason = "complex reasoning, strategy, or multi-requirement task"
    elif wide_score >= 1:
        mode = "wide"
        reason = "market, competitor, trend, or public-web context needed"
    else:
        mode = "atom"
        reason = "focused factual or technical lookup"

    return SearchModeProfile(
        mode=mode,
        reason=reason,
        settings=dict(MODE_SETTINGS[mode]),
        scores=scores,
        forced=False,
    )


def apply_search_mode_overrides(
    inner_kwargs: Dict[str, Any],
    profile: SearchModeProfile,
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Return a node-local config tuned for the selected search mode.

    Explicit environment overrides keep priority. This makes the dispatcher safe
    for experiments: users can still pin top-k, rerank mode, or retry limits.
    """
    environ = environ if environ is not None else os.environ
    tuned = dict(inner_kwargs)
    applied = {}

    for key, value in profile.settings.items():
        env_key = ENV_OVERRIDE_KEYS.get(key)
        if env_key and env_key in environ:
            continue
        if key == "kb_web_force_supplement" and inner_kwargs.get(key) is True:
            continue
        tuned[key] = value
        applied[key] = value

    tuned["search_mode"] = profile.mode
    tuned["search_mode_profile"] = profile.to_dict()
    tuned["search_mode_overrides"] = applied
    return tuned
