# coding:utf8

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .intent import classify_followup_intent
from .section_locator import find_target_sections, replace_section

try:
    from recursive.utils.markdown_tables import normalize_markdown_tables
except Exception:
    def normalize_markdown_tables(markdown):
        return markdown


def run_followup_edit(
    report: str,
    instruction: str,
    artifacts: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    max_sections: int = 1,
    edit_client: Any = None,
    enable_search_repair: bool = False,
    kb_name: Optional[str] = None,
    search_repair_topk: int = 3,
    search_repair_max_queries: int = 4,
    search_repair_max_results: int = 6,
    search_client: Any = None,
    search_repair_runner: Any = None,
) -> Tuple[str, Dict[str, Any]]:
    """Run a bounded follow-up edit on an existing report."""
    artifacts = artifacts or {}
    intent = classify_followup_intent(instruction)
    sections = find_target_sections(
        report=report,
        instruction=instruction,
        intent=intent,
        max_sections=max_sections,
    )
    edit_record = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "instruction": instruction,
        "intent": intent,
        "target_sections": [
            {
                "title": section.get("title"),
                "start_line": section.get("start_line"),
                "end_line": section.get("end_line"),
                "full_report": bool(section.get("full_report")),
            }
            for section in sections
        ],
        "requires_search_repair": intent.get("requires_search_repair", False),
        "search_repair_enabled": bool(enable_search_repair),
        "search_repair": {},
        "edited_section_count": 0,
        "skipped": [],
        "error": "",
    }
    if not sections:
        edit_record["skipped"].append("No editable section found.")
        return report, edit_record

    search_repair_report = _maybe_run_followup_search_repair(
        report=report,
        instruction=instruction,
        intent=intent,
        sections=sections,
        enabled=enable_search_repair,
        kb_name=kb_name,
        topk=search_repair_topk,
        max_queries=search_repair_max_queries,
        max_results=search_repair_max_results,
        search_client=search_client,
        search_repair_runner=search_repair_runner,
    )
    if search_repair_report:
        artifacts = dict(artifacts)
        artifacts["followup_search_repair"] = search_repair_report
        edit_record["search_repair"] = _compact_search_repair(search_repair_report)

    current_report = report
    for section in sections:
        payload = _build_edit_payload(
            report=current_report,
            section=section,
            instruction=instruction,
            intent=intent,
            artifacts=artifacts,
        )
        try:
            replacement = _call_followup_editor(
                payload=payload,
                model=model,
                edit_client=edit_client,
            )
        except Exception as exc:
            edit_record["error"] = str(exc)
            edit_record["skipped"].append(
                "Edit failed for {}: {}".format(section.get("title"), exc))
            continue
        replacement = _clean_editor_output(replacement)
        if not replacement:
            edit_record["skipped"].append(
                "Empty edit result for {}".format(section.get("title")))
            continue
        current_report = replace_section(current_report, section, replacement)
        edit_record["edited_section_count"] += 1

    current_report = normalize_markdown_tables(current_report)
    current_report = _append_followup_evidence_references(
        current_report,
        artifacts.get("followup_search_repair") or {},
    )
    edit_record["status"] = (
        "edited" if edit_record["edited_section_count"] > 0 else "unchanged")
    return current_report, edit_record


def save_followup_edit(path: str, edit_record: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(edit_record, f, indent=2, ensure_ascii=False)


def _build_edit_payload(
    report: str,
    section: Dict[str, Any],
    instruction: str,
    intent: Dict[str, Any],
    artifacts: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "instruction": instruction,
        "intent": intent,
        "section_title": section.get("title"),
        "section_markdown": section.get("markdown"),
        "full_report": bool(section.get("full_report")),
        "relevant_evidence": _evidence_for_section(
            section_title=section.get("title"),
            artifacts=artifacts,
        ),
        "claims_needing_review": _claims_for_section(
            section_title=section.get("title"),
            artifacts=artifacts,
        ),
        "report_outline": _report_outline(report),
    }


def _call_followup_editor(
    payload: Dict[str, Any],
    model: Optional[str] = None,
    edit_client: Any = None,
) -> str:
    if callable(edit_client):
        result = edit_client(payload)
        if isinstance(result, dict):
            return result.get("markdown", "") or result.get("section_markdown", "")
        return str(result or "")
    if not model:
        raise ValueError("Follow-up edit model is required when no edit_client is provided.")

    from recursive.llm.llm import OpenAIApiProxy

    prompt = """
You are editing an existing enterprise technical RAG report after a user follow-up.

Rules:
- Edit only the provided section unless full_report=true.
- Keep the same heading for section-level edits.
- Reuse provided evidence and citation labels when they support the new text.
- Do not invent citation labels or exact numbers.
- If the user asks for market/competitor/latest content but evidence is insufficient, add a concise "needs supplemental evidence" note instead of hallucinating.
- Keep Markdown tables valid and readable.
- Return only the edited Markdown, no JSON and no explanation.

Payload:
{}
""".strip().format(json.dumps(payload, ensure_ascii=False, indent=2))

    response = OpenAIApiProxy(verbose=False).call(
        model=model,
        messages=[
            {"role": "system", "content": "Return only edited Markdown."},
            {"role": "user", "content": prompt},
        ],
        no_cache=True,
        temperature=0.2,
        max_tokens=4096,
    )
    return response[0]["message"]["content"]


def _evidence_for_section(section_title: str, artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = _search_repair_evidence(artifacts.get("followup_search_repair") or {})

    graph = artifacts.get("evidence_graph") or {}
    nodes = graph.get("nodes") or []
    evidence_by_id = {}
    for node in nodes:
        if node.get("type") != "evidence":
            continue
        data = node.get("data") or {}
        evidence_id = data.get("evidence_id")
        if evidence_id:
            evidence_by_id[evidence_id] = data

    evidence_ids = []
    for item in (graph.get("summary") or {}).get("section_evidence_map") or []:
        if _same_title(item.get("section_title"), section_title):
            evidence_ids.extend(item.get("evidence_ids") or [])
    if not evidence_ids:
        evidence_ids = list(evidence_by_id.keys())[:8]

    seen_ids = {item.get("evidence_id") for item in results if item.get("evidence_id")}
    for evidence_id in evidence_ids[:10]:
        data = evidence_by_id.get(evidence_id)
        if not data:
            continue
        if evidence_id in seen_ids:
            continue
        seen_ids.add(evidence_id)
        results.append({
            "evidence_id": evidence_id,
            "source_type": data.get("source_type"),
            "source_title": data.get("source_title"),
            "citation_label": data.get("citation_label"),
            "verify_label": data.get("verify_label"),
            "preview": data.get("preview"),
        })
    return results[:12]


def _maybe_run_followup_search_repair(
    report: str,
    instruction: str,
    intent: Dict[str, Any],
    sections: List[Dict[str, Any]],
    enabled: bool,
    kb_name: Optional[str],
    topk: int,
    max_queries: int,
    max_results: int,
    search_client: Any = None,
    search_repair_runner: Any = None,
) -> Dict[str, Any]:
    if not enabled or not intent.get("requires_search_repair"):
        return {}

    writer_feedback = _build_followup_writer_feedback(instruction, intent, sections)
    if not (writer_feedback.get("actions") or []):
        return {}

    memory = _FollowupSearchMemory(_next_reference_index(report))
    root_goal = _followup_search_goal(instruction, sections)
    try:
        runner = search_repair_runner
        if not callable(runner):
            from recursive.evidence.search_repair import run_search_repair
            runner = run_search_repair
        return runner(
            writer_feedback=writer_feedback,
            root_goal=root_goal,
            memory=memory,
            language=None,
            kb_name=kb_name,
            execute_kb=True,
            kb_topk=max(1, int(topk or 3)),
            max_queries=max(1, int(max_queries or 4)),
            max_results=max(1, int(max_results or 6)),
            search_client=search_client,
        ) or {}
    except Exception as exc:
        return {
            "version": "1.0",
            "enabled": True,
            "executed": False,
            "kb_name": kb_name or "",
            "queries": [],
            "kb_results": [],
            "new_evidence_ids": [],
            "skipped": [],
            "error": str(exc),
            "summary": {
                "target_count": 0,
                "query_count": 0,
                "kb_result_count": 0,
                "new_evidence_count": 0,
                "executed": False,
            },
        }


class _FollowupSearchMemory:
    def __init__(self, global_start_index: int):
        self.global_start_index = max(1, int(global_start_index or 1))

    def add_search_result(self, page: Dict[str, Any]) -> Dict[str, Any]:
        index = page.get("global_index")
        if not isinstance(index, int) or index <= 0:
            index = self.global_start_index
            page["global_index"] = index
        self.global_start_index = max(self.global_start_index, index + 1)
        evidence = page.get("evidence") or {}
        if evidence:
            evidence["global_index"] = index
            evidence["citation_label"] = "[reference:{}]".format(index)
            page["evidence"] = evidence
            page["evidence_id"] = evidence.get("evidence_id") or page.get("evidence_id")
        return page


def _build_followup_writer_feedback(
    instruction: str,
    intent: Dict[str, Any],
    sections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    dimensions = _infer_followup_dimensions(instruction, intent)
    target_section = sections[0].get("title") if sections else ""
    actions = []
    for dimension in dimensions:
        actions.append({
            "action_type": "supplement_missing_rubric_dimension",
            "severity": "medium",
            "target_section": target_section,
            "target_rubric_dimension": dimension,
            "message": "Follow-up request needs supplemental KB evidence before local rewrite.",
            "claim_text": instruction if dimension == "claim_support" else "",
        })
    return {
        "version": "1.0",
        "source": "followup_edit",
        "actions": actions,
        "section_feedback": [
            {
                "section_title": section.get("title"),
                "citation_count": len(re.findall(r"\[(?:reference|KB|WEB):\d+\]", section.get("markdown") or "", re.IGNORECASE)),
                "unsupported_claim_count": 0,
                "partial_claim_count": 0,
            }
            for section in sections
        ],
    }


def _infer_followup_dimensions(instruction: str, intent: Dict[str, Any]) -> List[str]:
    text = str(instruction or "").lower()
    dimensions = []
    hints = [
        ("competitors", ("competitor", "competition", "vendor", "benchmark", "竞品", "竞争", "厂商", "对标")),
        ("market_context", ("market", "industry", "business", "市场", "行业", "商业", "规模", "趋势")),
        ("recent_external_context", ("latest", "recent", "news", "最新", "近期", "新闻", "动态")),
        ("application_scenarios", ("case", "scenario", "application", "案例", "场景", "应用", "落地")),
        ("challenges", ("risk", "challenge", "security", "风险", "挑战", "安全", "漏洞")),
        ("strategy_recommendation", ("roadmap", "strategy", "recommendation", "路线", "策略", "建议")),
        ("technology_definition", ("architecture", "technology", "definition", "架构", "技术", "定义", "原理")),
    ]
    for dimension, keys in hints:
        if any(key in text or key in str(instruction or "") for key in keys):
            dimensions.append(dimension)
    if intent.get("intent_type") == "verify_or_cite":
        dimensions.append("claim_support")
    if not dimensions:
        dimensions.append("claim_support")
    return _dedupe(dimensions, 4)


def _followup_search_goal(instruction: str, sections: List[Dict[str, Any]]) -> str:
    titles = "；".join(
        str(section.get("title") or "").strip()
        for section in sections[:3]
        if section.get("title")
    )
    if titles:
        return "{}\n目标章节：{}".format(instruction, titles)
    return instruction


def _search_repair_evidence(search_repair: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    for item in (search_repair or {}).get("kb_results") or []:
        evidence_id = item.get("evidence_id")
        results.append({
            "evidence_id": evidence_id,
            "source_type": item.get("source_type") or "kb",
            "source_title": item.get("title") or item.get("source") or "Local KB",
            "citation_label": item.get("citation_label"),
            "verify_label": item.get("verify_label"),
            "preview": item.get("summary"),
            "search_query": item.get("search_query"),
        })
    return results[:8]


def _append_followup_evidence_references(
    report: str,
    search_repair: Dict[str, Any],
) -> str:
    results = (search_repair or {}).get("kb_results") or []
    if not results:
        return report

    lines = []
    for item in results:
        label = item.get("citation_label")
        if not label or label not in report:
            continue
        if re.search(r"(?m)^-\s*{}(?:\s|$)".format(re.escape(label)), report):
            continue
        title = str(item.get("title") or item.get("source") or "Local KB").strip()
        source = str(item.get("source") or item.get("url") or "").strip()
        line = "- {} KB: {}".format(label, title)
        if source:
            line += "\n  Source: `{}`".format(source)
        lines.append(line)
    if not lines:
        return report

    base = str(report or "").rstrip()
    heading = "### Follow-up Evidence"
    if heading in base:
        return base + "\n" + "\n".join(lines) + "\n"
    return base + "\n\n{}\n{}\n".format(heading, "\n".join(lines))


def _compact_search_repair(search_repair: Dict[str, Any]) -> Dict[str, Any]:
    if not search_repair:
        return {}
    return {
        "enabled": bool(search_repair.get("enabled")),
        "executed": bool(search_repair.get("executed")),
        "kb_name": search_repair.get("kb_name", ""),
        "queries": list(search_repair.get("queries") or [])[:8],
        "new_evidence_ids": list(search_repair.get("new_evidence_ids") or [])[:12],
        "summary": search_repair.get("summary") or {},
        "skipped": list(search_repair.get("skipped") or [])[:6],
        "error": search_repair.get("error", ""),
        "kb_results": list(search_repair.get("kb_results") or [])[:8],
    }


def _next_reference_index(report: str) -> int:
    indices = []
    for pattern in (r"\[reference:(\d+)\]", r"\[KB:(\d+)\]", r"\[WEB:(\d+)\]"):
        indices.extend(int(match) for match in re.findall(pattern, str(report or ""), re.IGNORECASE))
    return max(indices or [0]) + 1


def _dedupe(items: List[Any], limit: Optional[int] = None) -> List[Any]:
    result = []
    seen = set()
    for item in items:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if limit is not None and len(result) >= limit:
            break
    return result


def _claims_for_section(section_title: str, artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
    verification = artifacts.get("claim_verification") or {}
    claims = []
    for claim in verification.get("claims") or []:
        if section_title and not _same_title(claim.get("section_title"), section_title):
            continue
        if claim.get("status") in ("unsupported", "partially_supported", "needs_review"):
            claims.append({
                "claim_id": claim.get("claim_id"),
                "text": claim.get("text"),
                "status": claim.get("status"),
                "risk_level": claim.get("risk_level"),
                "supporting_evidence_ids": claim.get("supporting_evidence_ids") or [],
            })
    return claims[:8]


def _report_outline(report: str) -> List[str]:
    return [
        match.group(2).strip()
        for match in re.finditer(r"(?m)^(#{1,4})\s+(.+?)\s*$", str(report or ""))
        if "reference" not in match.group(2).lower() and "参考" not in match.group(2)
    ][:30]


def _same_title(left: Any, right: Any) -> bool:
    return _norm_title(left) == _norm_title(right)


def _norm_title(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^[一二三四五六七八九十\d]+[、.．\s-]*", "", text)
    return re.sub(r"\s+", "", text)


def _clean_editor_output(text: Any) -> str:
    value = str(text or "").strip()
    fenced = re.search(r"```(?:markdown|md)?\s*(.*?)\s*```", value, re.DOTALL | re.IGNORECASE)
    if fenced:
        value = fenced.group(1).strip()
    return value
