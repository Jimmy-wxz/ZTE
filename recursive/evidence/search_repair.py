# coding:utf8

import hashlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from .ledger import annotate_page_evidence


try:
    from recursive.search.query import build_rubric_gap_queries, infer_page_source_type
except Exception:
    import importlib.util

    _QUERY_PATH = Path(__file__).resolve().parents[1] / "search" / "query.py"
    _QUERY_SPEC = importlib.util.spec_from_file_location(
        "search_query_for_search_repair", _QUERY_PATH)
    _QUERY_MODULE = importlib.util.module_from_spec(_QUERY_SPEC)
    _QUERY_SPEC.loader.exec_module(_QUERY_MODULE)
    build_rubric_gap_queries = _QUERY_MODULE.build_rubric_gap_queries
    infer_page_source_type = _QUERY_MODULE.infer_page_source_type


SEARCH_ACTION_TYPES = {
    "supplement_missing_rubric_dimension",
    "supplement_web_context",
    "rewrite_or_cite_claim",
}

SECTION_TITLE_HINTS = {
    "competitors": ("competitor", "competition", "vendor", "benchmark", "对标", "竞品", "竞争", "厂商"),
    "market_context": ("market", "industry", "business", "市场", "行业", "商业"),
    "recent_external_context": ("recent", "latest", "news", "最新", "近期", "外部"),
    "application_scenarios": ("application", "scenario", "case", "应用", "场景", "案例"),
    "technology_definition": ("architecture", "technology", "definition", "架构", "技术", "定义"),
    "challenges": ("risk", "challenge", "limitation", "风险", "挑战", "问题"),
    "strategy_recommendation": ("roadmap", "strategy", "recommendation", "路线", "策略", "建议"),
    "claim_support": ("roadmap", "risk", "market", "analysis", "路线", "风险", "市场", "分析"),
}

FALLBACK_QUERY_TERMS = {
    "competitors": {
        "zh": ("竞品对比 厂商分析", "竞争格局 产品能力 安全能力"),
        "en": ("competitor comparison vendor analysis", "competitive landscape product capability security"),
    },
    "market_context": {
        "zh": ("市场规模 趋势 2026", "商业机会 增长预测 行业需求"),
        "en": ("market size trends 2026", "business opportunity growth forecast demand"),
    },
    "recent_external_context": {
        "zh": ("最新进展 2026 公开资料", "近期新闻 行业动态"),
        "en": ("latest developments 2026 public sources", "recent news industry updates"),
    },
    "application_scenarios": {
        "zh": ("应用场景 落地案例 部署实践", "行业应用 使用场景"),
        "en": ("application scenarios deployment case studies", "industry use cases"),
    },
    "technology_definition": {
        "zh": ("技术架构 原理 能力指标", "定义 架构 核心能力"),
        "en": ("technical architecture principles capabilities metrics", "definition architecture core capabilities"),
    },
    "challenges": {
        "zh": ("挑战 风险 难点 局限", "实施障碍 痛点"),
        "en": ("challenges risks limitations barriers", "implementation barriers pain points"),
    },
    "strategy_recommendation": {
        "zh": ("策略建议 路线图 发展方向", "实施建议 商业策略"),
        "en": ("strategy recommendations roadmap direction", "implementation recommendations business strategy"),
    },
    "claim_support": {
        "zh": ("证据 来源 验证", "案例 数据 支撑"),
        "en": ("evidence source validation", "case data support"),
    },
}


def build_search_repair_plan(
    writer_feedback: Optional[Dict[str, Any]],
    root_goal: str = "",
    language: Optional[str] = None,
    max_queries: int = 6,
) -> Dict[str, Any]:
    """Build a targeted supplemental-search plan from writer/rubric feedback."""
    writer_feedback = writer_feedback or {}
    lang = _normal_language(language or _infer_language(root_goal))
    core = _core_topic(root_goal)
    targets = _collect_search_targets(writer_feedback)

    all_queries: List[str] = []
    for target in targets:
        queries = _target_queries(core, lang, target)
        target["queries"] = queries
        all_queries.extend(queries)

    queries = _dedupe(all_queries, max_queries)
    return {
        "version": "1.0",
        "enabled": bool(targets),
        "root_goal": root_goal,
        "language": lang,
        "core_topic": core,
        "targets": targets,
        "queries": queries,
        "summary": {
            "target_count": len(targets),
            "query_count": len(queries),
            "web_required_count": sum(
                1 for target in targets
                if target.get("source_preference") in ("web", "kb+web")
            ),
        },
    }


def run_search_repair(
    writer_feedback: Optional[Dict[str, Any]],
    root_goal: str = "",
    memory: Any = None,
    language: Optional[str] = None,
    kb_name: Optional[str] = None,
    execute_kb: bool = True,
    kb_topk: int = 3,
    max_queries: int = 6,
    max_results: int = 10,
    verify_mode: str = "heuristic",
    search_client: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """Run bounded KB supplemental search for rubric/feedback gaps.

    Web gaps are kept as auditable plan items. This avoids adding another
    SerpAPI call to the default repair path while still recording what should
    be searched when a full external repair pass is enabled later.
    """
    plan = build_search_repair_plan(
        writer_feedback=writer_feedback,
        root_goal=root_goal,
        language=language,
        max_queries=max_queries,
    )
    report = deepcopy(plan)
    report.update({
        "executed": False,
        "execute_kb": bool(execute_kb),
        "kb_name": kb_name or os.environ.get("WRITEHERE_KB_NAME", ""),
        "kb_results": [],
        "new_evidence_ids": [],
        "skipped": [],
        "error": "",
    })

    if not report["enabled"]:
        report["skipped"].append("No rubric or claim gaps require supplemental search.")
        _refresh_summary(report)
        return report
    if not execute_kb:
        report["skipped"].append("KB repair execution disabled; search plan only.")
        _refresh_summary(report)
        return report
    if not report["queries"]:
        report["skipped"].append("No supplemental search queries generated.")
        _refresh_summary(report)
        return report

    seen_pages = set()
    try:
        for query in report["queries"][: max(0, int(max_queries or 0))]:
            pages = _search_pages(
                query=query,
                kb_name=report["kb_name"],
                kb_topk=kb_topk,
                memory=memory,
                search_client=search_client,
            )
            for page in pages:
                if len(report["kb_results"]) >= max_results:
                    break
                key = _page_key(page)
                if key in seen_pages:
                    continue
                seen_pages.add(key)
                page.setdefault("search_query", query)
                page.setdefault("title", "Local KB")
                page.setdefault("url", "local-kb://{}".format(page.get("source", "unknown")))
                source_type = infer_page_source_type(page, default="kb")
                annotate_page_evidence(
                    page,
                    node_id="search_repair",
                    node_goal=root_goal,
                    sub_question=query,
                    source_type=source_type,
                    verify_mode=verify_mode,
                )
                if memory is not None and hasattr(memory, "add_search_result"):
                    page = memory.add_search_result(page)
                evidence = page.get("evidence") or {}
                evidence_id = evidence.get("evidence_id") or page.get("evidence_id")
                if evidence_id:
                    report["new_evidence_ids"].append(evidence_id)
                report["kb_results"].append(_result_summary(page, query))
        report["executed"] = True
    except Exception as exc:
        report["error"] = str(exc)

    _refresh_summary(report)
    return report


def augment_writer_feedback_with_search_repair(
    writer_feedback: Optional[Dict[str, Any]],
    search_repair: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Attach supplemental evidence hints so the writer repair loop can use them."""
    updated = deepcopy(writer_feedback or {})
    search_repair = search_repair or {}
    evidence_ids = _dedupe(search_repair.get("new_evidence_ids") or [])
    updated["search_repair"] = search_repair
    updated["search_repair_evidence_ids"] = evidence_ids

    target_sections = _target_sections_for_repair(updated, search_repair)
    for section in updated.get("section_feedback") or []:
        title = section.get("section_title")
        if target_sections and title not in target_sections:
            continue
        existing = list(section.get("search_repair_evidence_ids") or [])
        for evidence_id in evidence_ids:
            if evidence_id not in existing:
                existing.append(evidence_id)
        section["search_repair_evidence_ids"] = existing

    _add_section_repair_actions(updated, search_repair, target_sections)
    summary = updated.setdefault("summary", {})
    summary["search_repair_evidence_count"] = len(evidence_ids)
    summary["search_repair_query_count"] = len(search_repair.get("queries") or [])
    if evidence_ids:
        summary["repair_needed"] = True
    return updated


def save_search_repair(path: str, report: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def _collect_search_targets(writer_feedback: Dict[str, Any]) -> List[Dict[str, Any]]:
    targets = []
    seen = set()
    for action in writer_feedback.get("actions") or []:
        action_type = action.get("action_type")
        if action_type not in SEARCH_ACTION_TYPES:
            continue
        if action_type == "supplement_web_context":
            source_preference = "kb+web"
        else:
            source_preference = "kb"
        dimension_id = action.get("target_rubric_dimension") or "claim_support"
        claim_text = action.get("claim_text", "")
        key = (
            action_type,
            dimension_id,
            action.get("target_section"),
            claim_text[:120],
        )
        if key in seen:
            continue
        seen.add(key)
        targets.append({
            "action_type": action_type,
            "severity": action.get("severity", "medium"),
            "target_section": action.get("target_section"),
            "target_rubric_dimension": dimension_id,
            "source_preference": source_preference,
            "claim_text": claim_text,
            "message": action.get("message", ""),
        })
    return targets


def _target_queries(core: str, language: str, target: Dict[str, Any]) -> List[str]:
    dimension = target.get("target_rubric_dimension") or "claim_support"
    if target.get("action_type") == "rewrite_or_cite_claim":
        return _dedupe([
            "{} {}".format(core, _trim_query(target.get("claim_text"), 80)),
            *_fallback_queries(core, language, "claim_support"),
        ], 3)

    gap = {"missing_required": [], "preferred_web_missing": []}
    if target.get("action_type") == "supplement_web_context":
        gap["preferred_web_missing"] = [dimension]
    else:
        gap["missing_required"] = [dimension]
    queries = build_rubric_gap_queries(core, language, gap)
    queries.extend(_fallback_queries(core, language, dimension))
    return _dedupe(queries, 3)


def _fallback_queries(core: str, language: str, dimension: str) -> List[str]:
    terms = FALLBACK_QUERY_TERMS.get(dimension) or FALLBACK_QUERY_TERMS["claim_support"]
    suffixes = terms.get(language) or terms.get("en") or ()
    return ["{} {}".format(core, suffix).strip() for suffix in suffixes if suffix]


def _search_pages(
    query: str,
    kb_name: str,
    kb_topk: int,
    memory: Any = None,
    search_client: Optional[Callable[..., Any]] = None,
) -> List[Dict[str, Any]]:
    if callable(search_client):
        return _call_search_client(search_client, query, kb_topk)
    if not kb_name:
        return []

    from recursive.executor.actions.local_knowledge_base import LocalKnowledgeBase

    action = LocalKnowledgeBase(knowledge_base_name=kb_name, topk=kb_topk)
    result = action.search(
        query_list=[query],
        user_question=query,
        think="Rubric-guided search repair",
        global_start_index=getattr(memory, "global_start_index", 1),
    )
    return list(result.get("web_pages") or [])


def _call_search_client(search_client: Callable[..., Any], query: str, topk: int) -> List[Dict[str, Any]]:
    try:
        result = search_client(query=query, topk=topk)
    except TypeError:
        try:
            result = search_client(query, topk)
        except TypeError:
            result = search_client(query)
    if isinstance(result, dict):
        if "web_pages" in result:
            return list(result.get("web_pages") or [])
        if "results" in result:
            return list(result.get("results") or [])
    if isinstance(result, list):
        return result
    return []


def _target_sections_for_repair(
    writer_feedback: Dict[str, Any],
    search_repair: Dict[str, Any],
) -> set:
    sections = {
        target.get("target_section")
        for target in search_repair.get("targets") or []
        if target.get("target_section")
    }
    if sections:
        return sections

    section_feedback = writer_feedback.get("section_feedback") or []
    for target in search_repair.get("targets") or []:
        dimension = target.get("target_rubric_dimension")
        matched = _match_section_by_dimension(section_feedback, dimension)
        if matched:
            sections.add(matched)
    if sections:
        return sections

    for section in section_feedback:
        if (
            section.get("citation_count", 0) < 2
            or section.get("unsupported_claim_count", 0) > 0
            or section.get("partial_claim_count", 0) > 0
        ):
            title = section.get("section_title")
            if title:
                sections.add(title)
    if sections:
        return sections

    if section_feedback:
        title = section_feedback[0].get("section_title")
        return {title} if title else set()
    return set()


def _add_section_repair_actions(
    writer_feedback: Dict[str, Any],
    search_repair: Dict[str, Any],
    target_sections: Iterable[str],
) -> None:
    evidence_ids = search_repair.get("new_evidence_ids") or []
    if not evidence_ids:
        return
    actions = writer_feedback.setdefault("actions", [])
    seen = {
        (
            action.get("action_type"),
            action.get("target_section"),
            action.get("search_repair_dimension"),
        )
        for action in actions
    }
    target_dimensions = _dedupe(
        target.get("target_rubric_dimension")
        for target in search_repair.get("targets") or []
    )
    for section in target_sections:
        for dimension in target_dimensions or ["claim_support"]:
            key = ("minimal_section_rewrite", section, dimension)
            if key in seen:
                continue
            actions.append({
                "action_type": "minimal_section_rewrite",
                "severity": "medium",
                "target_section": section,
                "search_repair_dimension": dimension,
                "message": "Use supplemental search-repair evidence to cover the missing rubric point or cite the weak claim.",
                "search_repair_evidence_ids": evidence_ids[:8],
            })
            seen.add(key)


def _match_section_by_dimension(
    section_feedback: List[Dict[str, Any]],
    dimension: str,
) -> str:
    hints = SECTION_TITLE_HINTS.get(dimension or "", ())
    for section in section_feedback:
        title = str(section.get("section_title") or "")
        normalized = title.lower()
        if any(hint.lower() in normalized for hint in hints):
            return section.get("section_title")
    return ""


def _result_summary(page: Dict[str, Any], query: str) -> Dict[str, Any]:
    evidence = page.get("evidence") or {}
    return {
        "evidence_id": evidence.get("evidence_id") or page.get("evidence_id"),
        "citation_label": evidence.get("citation_label"),
        "source_type": evidence.get("source_type") or infer_page_source_type(page, default="kb"),
        "verify_label": evidence.get("verify_label"),
        "verify_score": evidence.get("verify_score", 0.0),
        "title": page.get("title"),
        "url": page.get("url"),
        "source": page.get("source"),
        "chunk_index": page.get("chunk_index"),
        "search_query": query,
        "summary": _trim_query(page.get("summary") or page.get("text"), 260),
    }


def _refresh_summary(report: Dict[str, Any]) -> None:
    summary = report.setdefault("summary", {})
    summary.update({
        "target_count": len(report.get("targets") or []),
        "query_count": len(report.get("queries") or []),
        "web_required_count": sum(
            1 for target in report.get("targets") or []
            if target.get("source_preference") in ("web", "kb+web")
        ),
        "kb_result_count": len(report.get("kb_results") or []),
        "new_evidence_count": len(report.get("new_evidence_ids") or []),
        "executed": bool(report.get("executed")),
    })


def _page_key(page: Dict[str, Any]) -> str:
    source = str(page.get("source") or page.get("url") or page.get("title") or "")
    chunk = str(page.get("chunk_index", ""))
    text = str(page.get("summary") or page.get("text") or "")[:300]
    payload = "{}\n{}\n{}".format(source, chunk, text)
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()


def _normal_language(language: str) -> str:
    return "zh" if str(language or "").lower().startswith("zh") else "en"


def _infer_language(text: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", str(text or "")) else "en"


def _core_topic(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    if not value:
        return ""
    parts = re.split(r"[。；;？?\n]", value)
    core = parts[0].strip() if parts else value
    return _trim_query(core, 90)


def _trim_query(value: Any, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip()


def _dedupe(items: Iterable[Any], limit: Optional[int] = None) -> List[str]:
    result = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result
