# coding:utf8

import json
import os
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional


def build_writer_feedback(
    claim_verification: Optional[Dict[str, Any]] = None,
    quality_audit: Optional[Dict[str, Any]] = None,
    evidence_graph: Optional[Dict[str, Any]] = None,
    root_node_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build section-level feedback for later writer repair or supplemental search."""
    claim_verification = claim_verification or {}
    quality_audit = quality_audit or {}
    evidence_graph = evidence_graph or {}
    root_node_json = root_node_json or {}

    section_feedback = _build_section_feedback(
        claim_verification=claim_verification,
        quality_audit=quality_audit,
        evidence_graph=evidence_graph,
    )
    actions = _build_feedback_actions(
        section_feedback=section_feedback,
        claim_verification=claim_verification,
        quality_audit=quality_audit,
        rubric_gaps=list(_iter_rubric_gaps(root_node_json)),
    )
    severity_counts = Counter(action["severity"] for action in actions)
    action_type_counts = Counter(action["action_type"] for action in actions)

    return {
        "version": "1.0",
        "section_feedback": section_feedback,
        "actions": actions,
        "summary": {
            "section_count": len(section_feedback),
            "action_count": len(actions),
            "severity_counts": dict(severity_counts),
            "action_type_counts": dict(action_type_counts),
            "repair_needed": any(action["severity"] in ("high", "medium") for action in actions),
        },
    }


def save_writer_feedback(path: str, feedback: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feedback, f, indent=2, ensure_ascii=False)


def _build_section_feedback(
    claim_verification: Dict[str, Any],
    quality_audit: Dict[str, Any],
    evidence_graph: Dict[str, Any],
) -> List[Dict[str, Any]]:
    sections = {}

    for item in quality_audit.get("section_citation_metrics") or []:
        title = item.get("title") or "Untitled"
        sections[title] = {
            "section_title": title,
            "start_line": item.get("start_line"),
            "end_line": item.get("end_line"),
            "citation_count": item.get("citation_count", 0),
            "char_count": item.get("char_count", 0),
            "unsupported_claim_count": 0,
            "partial_claim_count": 0,
            "claims_needing_review": [],
            "evidence_ids": [],
            "kb_evidence_count": 0,
            "web_evidence_count": 0,
            "rubric_dimensions": [],
        }

    for claim in claim_verification.get("claims") or []:
        title = claim.get("section_title") or "Untitled"
        section = sections.setdefault(title, {
            "section_title": title,
            "start_line": None,
            "end_line": None,
            "citation_count": 0,
            "char_count": 0,
            "unsupported_claim_count": 0,
            "partial_claim_count": 0,
            "claims_needing_review": [],
            "evidence_ids": [],
            "kb_evidence_count": 0,
            "web_evidence_count": 0,
            "rubric_dimensions": [],
        })
        status = claim.get("status")
        if status == "unsupported":
            section["unsupported_claim_count"] += 1
        if status in ("partially_supported", "needs_review"):
            section["partial_claim_count"] += 1
        if status in ("unsupported", "partially_supported", "needs_review"):
            section["claims_needing_review"].append({
                "claim_id": claim.get("claim_id"),
                "text": claim.get("text"),
                "status": status,
                "risk_level": claim.get("risk_level"),
                "line_number": claim.get("line_number"),
            })
        for evidence_id in claim.get("supporting_evidence_ids") or []:
            if evidence_id not in section["evidence_ids"]:
                section["evidence_ids"].append(evidence_id)

    for entry in (evidence_graph.get("summary") or {}).get("section_evidence_map") or []:
        title = entry.get("section_title") or "Untitled"
        section = sections.setdefault(title, {
            "section_title": title,
            "start_line": entry.get("start_line"),
            "end_line": entry.get("end_line"),
            "citation_count": entry.get("citation_count", 0),
            "char_count": 0,
            "unsupported_claim_count": 0,
            "partial_claim_count": 0,
            "claims_needing_review": [],
            "evidence_ids": [],
            "kb_evidence_count": 0,
            "web_evidence_count": 0,
            "rubric_dimensions": [],
        })
        for evidence_id in entry.get("evidence_ids") or []:
            if evidence_id not in section["evidence_ids"]:
                section["evidence_ids"].append(evidence_id)
        section["kb_evidence_count"] = entry.get("kb_evidence_count", section["kb_evidence_count"])
        section["web_evidence_count"] = entry.get("web_evidence_count", section["web_evidence_count"])
        section["rubric_dimensions"] = entry.get("rubric_dimensions", section["rubric_dimensions"])

    return list(sections.values())


def _build_feedback_actions(
    section_feedback: List[Dict[str, Any]],
    claim_verification: Dict[str, Any],
    quality_audit: Dict[str, Any],
    rubric_gaps: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    actions = []
    for claim in claim_verification.get("unsupported_claims") or []:
        actions.append({
            "action_type": "rewrite_or_cite_claim",
            "severity": "high" if claim.get("risk_level") == "high" else "medium",
            "target_section": claim.get("section_title"),
            "target_claim_id": claim.get("claim_id"),
            "message": "Claim has no sufficient evidence. Add a citation from retrieved evidence, trigger supplemental search, or rewrite it as an estimate/uncertain statement.",
            "claim_text": claim.get("text"),
        })

    for section in quality_audit.get("low_citation_sections") or []:
        actions.append({
            "action_type": "increase_section_citations",
            "severity": "medium",
            "target_section": section.get("title"),
            "message": "Section is long but has fewer than two citations. Reuse relevant KB/Web evidence or split unsupported analysis into clearly marked assumptions.",
            "citation_count": section.get("citation_count", 0),
            "char_count": section.get("char_count", 0),
        })

    seen_dims = set()
    for gap in rubric_gaps:
        for dimension_id in (gap.get("missing_required") or []):
            if dimension_id in seen_dims:
                continue
            seen_dims.add(dimension_id)
            actions.append({
                "action_type": "supplement_missing_rubric_dimension",
                "severity": "high",
                "target_rubric_dimension": dimension_id,
                "message": "Required rubric dimension is not covered by supported evidence. Trigger supplemental KB/Web search and add a focused paragraph.",
            })
        for dimension_id in (gap.get("preferred_web_missing") or []):
            key = "web:{}".format(dimension_id)
            if key in seen_dims:
                continue
            seen_dims.add(key)
            actions.append({
                "action_type": "supplement_web_context",
                "severity": "medium",
                "target_rubric_dimension": dimension_id,
                "message": "Rubric prefers public web evidence for this dimension. Add targeted web search and cite public sources.",
            })

    for section in section_feedback:
        if section.get("unsupported_claim_count", 0) == 0 and section.get("partial_claim_count", 0) == 0:
            continue
        actions.append({
            "action_type": "minimal_section_rewrite",
            "severity": "medium",
            "target_section": section.get("section_title"),
            "message": "Rewrite only the unsupported or weakly supported sentences in this section; keep supported cited content unchanged.",
            "claims_needing_review": section.get("claims_needing_review", [])[:5],
        })

    return _dedupe_actions(actions)


def _iter_rubric_gaps(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        if "dimensions" in obj and (
            "missing_required" in obj or
            "preferred_web_missing" in obj or
            "required_coverage" in obj
        ):
            yield obj
        for value in obj.values():
            yield from _iter_rubric_gaps(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_rubric_gaps(item)


def _dedupe_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    seen = set()
    for action in actions:
        key = (
            action.get("action_type"),
            action.get("target_section"),
            action.get("target_claim_id"),
            action.get("target_rubric_dimension"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return result
