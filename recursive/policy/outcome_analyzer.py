# coding:utf8

import json
import os
import re
from datetime import datetime
from typing import Any, Dict


def build_policy_outcome(
    task_id: str,
    prompt: str,
    decision: Dict[str, Any],
    result: str = "",
    timing: Dict[str, Any] = None,
    evidence_graph: Dict[str, Any] = None,
    claim_verification: Dict[str, Any] = None,
    writer_feedback: Dict[str, Any] = None,
    search_repair: Dict[str, Any] = None,
    repair_report: Dict[str, Any] = None,
    quality_audit: Dict[str, Any] = None,
    status: str = "completed",
    error: str = "",
) -> Dict[str, Any]:
    """Build outcome metrics for one report run."""
    timing = timing or {}
    evidence_graph = evidence_graph or {}
    claim_verification = claim_verification or {}
    writer_feedback = writer_feedback or {}
    search_repair = search_repair or {}
    repair_report = repair_report or {}
    quality_audit = quality_audit or {}
    result = str(result or "")

    quality = _quality_metrics(
        result=result,
        evidence_graph=evidence_graph,
        claim_verification=claim_verification,
        writer_feedback=writer_feedback,
        search_repair=search_repair,
        repair_report=repair_report,
        quality_audit=quality_audit,
    )
    scores = _scores(quality, timing, status=status)

    return {
        "version": "1.0",
        "task_id": task_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "error": error,
        "prompt_hash": (decision.get("features") or {}).get("prompt_hash", ""),
        "decision_summary": {
            "recommended_search_mode": (decision.get("recommendation") or {}).get("search_mode"),
            "recommended_model_profile": (decision.get("recommendation") or {}).get("model_profile"),
            "applied_to_runtime": decision.get("applied_to_runtime", False),
        },
        "timing": _normalize_timing(timing),
        "quality": quality,
        "scores": scores,
    }


def save_policy_outcome(path: str, outcome: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(outcome, f, indent=2, ensure_ascii=False)


def _quality_metrics(
    result: str,
    evidence_graph: Dict[str, Any],
    claim_verification: Dict[str, Any],
    writer_feedback: Dict[str, Any],
    search_repair: Dict[str, Any],
    repair_report: Dict[str, Any],
    quality_audit: Dict[str, Any],
) -> Dict[str, Any]:
    graph_summary = evidence_graph.get("summary") or {}
    claim_summary = claim_verification.get("summary") or {}
    writer_summary = writer_feedback.get("summary") or {}
    search_summary = search_repair.get("summary") or {}
    source_counts = graph_summary.get("source_type_counts") or {}

    citation_count = len(re.findall(r"\[(?:KB|WEB):\d+\]|\[reference:\d+\]", result))
    table_count = result.count("\n|")
    section_count = len(re.findall(r"(?m)^#{1,4}\s+\S+", result))
    report_chars = len(result)
    return {
        "report_char_count": report_chars,
        "section_count": section_count,
        "table_count": table_count,
        "citation_count": citation_count,
        "citation_per_1000_chars": round(citation_count * 1000.0 / max(1, report_chars), 4),
        "evidence_total": graph_summary.get("evidence_total", 0),
        "cited_evidence": graph_summary.get("cited_evidence", 0),
        "kb_evidence_count": source_counts.get("kb", 0),
        "web_evidence_count": source_counts.get("web", 0),
        "source_type_counts": source_counts,
        "rubric_missing_count": len(graph_summary.get("rubric_missing") or []),
        "unsupported_claim_count": claim_summary.get("unsupported_count", 0),
        "needs_review_claim_count": claim_summary.get("needs_review_count", 0),
        "low_citation_section_count": quality_audit.get("low_citation_section_count", 0),
        "unsupported_quantitative_count": quality_audit.get(
            "unsupported_quantitative_count", 0),
        "writer_action_count": writer_summary.get("action_count", 0),
        "search_repair_new_evidence_count": search_summary.get("new_evidence_count", 0),
        "repair_attempted_section_count": repair_report.get("attempted_section_count", 0),
        "repair_repaired_section_count": repair_report.get("repaired_section_count", 0),
    }


def _scores(quality: Dict[str, Any], timing: Dict[str, Any], status: str) -> Dict[str, Any]:
    if status != "completed":
        return {
            "quality_score": 0.0,
            "cost_penalty": 0.0,
            "reward": -50.0,
        }
    score = 55.0
    score += min(18.0, quality.get("citation_per_1000_chars", 0.0) * 3.0)
    score += min(12.0, quality.get("cited_evidence", 0) * 1.2)
    score += min(8.0, len(quality.get("source_type_counts") or {}) * 3.0)
    score += min(6.0, quality.get("search_repair_new_evidence_count", 0) * 1.5)
    score -= min(30.0, quality.get("unsupported_claim_count", 0) * 8.0)
    score -= min(20.0, quality.get("unsupported_quantitative_count", 0) * 6.0)
    score -= min(12.0, quality.get("low_citation_section_count", 0) * 3.0)
    score -= min(10.0, quality.get("rubric_missing_count", 0) * 4.0)
    score = max(0.0, min(100.0, score))

    duration = float(timing.get("total_duration_seconds", 0.0) or 0.0)
    cost_penalty = round(min(25.0, duration / 30.0), 4)
    reward = round(score - cost_penalty, 4)
    return {
        "quality_score": round(score, 4),
        "cost_penalty": cost_penalty,
        "reward": reward,
    }


def _normalize_timing(timing: Dict[str, Any]) -> Dict[str, Any]:
    result = {}
    for key, value in (timing or {}).items():
        try:
            result[key] = round(float(value), 4)
        except Exception:
            result[key] = value
    return result
