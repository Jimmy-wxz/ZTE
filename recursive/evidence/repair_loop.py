# coding:utf8

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .graph import HEADING_RE


def run_writer_repair_loop(
    article: str,
    writer_feedback: Dict[str, Any],
    memory: Any = None,
    ledger_items: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    max_sections: int = 2,
    repair_client: Any = None,
) -> Tuple[str, Dict[str, Any]]:
    """Run one bounded section-level repair pass using writer feedback."""
    report = {
        "version": "1.0",
        "enabled": True,
        "attempted_section_count": 0,
        "repaired_section_count": 0,
        "repaired_sections": [],
        "skipped": [],
        "error": "",
    }
    actions = _select_repair_actions(writer_feedback, max_sections=max_sections)
    if not actions:
        report["enabled"] = False
        report["skipped"].append("No actionable writer feedback.")
        return article, report

    items = ledger_items if ledger_items is not None else _ledger_items_from_memory(memory)
    evidence_by_id = {
        str(item.get("evidence_id")): item
        for item in items
        if item.get("evidence_id")
    }

    current_article = article
    for section_title, section_actions in actions:
        section = _find_section_block(current_article, section_title)
        if not section:
            report["skipped"].append("Section not found: {}".format(section_title))
            continue
        report["attempted_section_count"] += 1
        payload = _build_repair_payload(
            section=section,
            actions=section_actions,
            evidence_by_id=evidence_by_id,
            writer_feedback=writer_feedback,
        )
        try:
            repaired_section = _call_repair_writer(
                payload=payload,
                model=model,
                repair_client=repair_client,
            )
        except Exception as exc:
            report["error"] = str(exc)
            report["skipped"].append("Repair failed for {}: {}".format(section_title, exc))
            continue

        repaired_section = _clean_repaired_section(repaired_section)
        if not repaired_section:
            report["skipped"].append("Empty repair result for {}".format(section_title))
            continue
        current_article = _replace_section_block(current_article, section, repaired_section)
        report["repaired_section_count"] += 1
        report["repaired_sections"].append({
            "section_title": section_title,
            "action_count": len(section_actions),
            "start_line": section["start_line"],
            "end_line": section["end_line"],
        })

    return current_article, report


def save_repair_report(path: str, report: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def _select_repair_actions(
    writer_feedback: Dict[str, Any],
    max_sections: int = 2,
) -> List[Tuple[str, List[Dict[str, Any]]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    priorities = {}
    for action in writer_feedback.get("actions") or []:
        section = action.get("target_section")
        if not section:
            continue
        if action.get("action_type") not in (
            "rewrite_or_cite_claim",
            "increase_section_citations",
            "minimal_section_rewrite",
        ):
            continue
        grouped.setdefault(section, []).append(action)
        priorities[section] = max(priorities.get(section, 0), _action_priority(action))

    ordered = sorted(
        grouped.items(),
        key=lambda item: (-priorities.get(item[0], 0), item[0]),
    )
    return ordered[:max(0, int(max_sections or 0))]


def _action_priority(action: Dict[str, Any]) -> int:
    score = 0
    if action.get("severity") == "high":
        score += 5
    elif action.get("severity") == "medium":
        score += 3
    if action.get("action_type") == "rewrite_or_cite_claim":
        score += 3
    if action.get("action_type") == "minimal_section_rewrite":
        score += 2
    return score


def _build_repair_payload(
    section: Dict[str, Any],
    actions: List[Dict[str, Any]],
    evidence_by_id: Dict[str, Dict[str, Any]],
    writer_feedback: Dict[str, Any],
) -> Dict[str, Any]:
    section_feedback = _section_feedback_by_title(writer_feedback).get(section["title"], {})
    evidence_ids = list(section_feedback.get("evidence_ids") or [])
    for evidence_id in section_feedback.get("search_repair_evidence_ids") or []:
        if evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
    for evidence_id in writer_feedback.get("search_repair_evidence_ids") or []:
        if evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
    for action in actions:
        for evidence_id in action.get("search_repair_evidence_ids") or []:
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
        for claim in action.get("claims_needing_review") or []:
            for evidence_id in claim.get("supporting_evidence_ids") or []:
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
    evidence = []
    for evidence_id in evidence_ids[:10]:
        item = evidence_by_id.get(evidence_id)
        if not item:
            continue
        evidence.append({
            "evidence_id": evidence_id,
            "source_type": item.get("source_type"),
            "source_title": item.get("source_title"),
            "citation_label": item.get("citation_label"),
            "text": _trim(item.get("chunk_text"), 900),
        })
    return {
        "section_title": section["title"],
        "section_markdown": section["markdown"],
        "actions": actions,
        "section_feedback": section_feedback,
        "evidence": evidence,
    }


def _call_repair_writer(
    payload: Dict[str, Any],
    model: Optional[str] = None,
    repair_client: Any = None,
) -> str:
    if callable(repair_client):
        result = repair_client(payload)
        if isinstance(result, dict):
            return result.get("section_markdown", "")
        return str(result or "")
    if not model:
        raise ValueError("Repair model is required when no repair_client is provided.")

    from recursive.llm.llm import OpenAIApiProxy

    prompt = """
You are repairing one section of a Chinese technical RAG report.
Rewrite only the provided section. Keep the same section heading.

Rules:
- Preserve valid citations like [reference:N] when the evidence supports the sentence.
- You may add citation labels from the provided evidence list when they support the sentence.
- Do not invent citation numbers outside the provided evidence list.
- Remove unsupported exact numbers, ROI, cost, market-size, CVE, 0-day, or competitor capability claims.
- If a useful unsupported estimate must remain, clearly mark it as an estimate / needs validation.
- Keep Markdown tables valid and readable.
- Return only the repaired section Markdown, no JSON and no explanation.

Repair payload:
{}
""".strip().format(json.dumps(payload, ensure_ascii=False, indent=2))

    response = OpenAIApiProxy(verbose=False).call(
        model=model,
        messages=[
            {"role": "system", "content": "Return only the repaired Markdown section."},
            {"role": "user", "content": prompt},
        ],
        no_cache=True,
        temperature=0.2,
        max_tokens=4096,
    )
    return response[0]["message"]["content"]


def _find_section_block(article: str, section_title: str) -> Optional[Dict[str, Any]]:
    lines = _split_lines(article)
    wanted = _normalize_title(section_title)
    for idx, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        title = match.group(2).strip()
        if _normalize_title(title) != wanted:
            continue
        level = len(match.group(1))
        end = len(lines)
        for next_idx in range(idx + 1, len(lines)):
            next_match = HEADING_RE.match(lines[next_idx].strip())
            if next_match and len(next_match.group(1)) <= level:
                end = next_idx
                break
        return {
            "title": title,
            "start_line": idx + 1,
            "end_line": end,
            "start_index": idx,
            "end_index": end,
            "markdown": "\n".join(lines[idx:end]).strip(),
        }
    return None


def _replace_section_block(article: str, section: Dict[str, Any], repaired_section: str) -> str:
    lines = _split_lines(article)
    replacement = _split_lines(repaired_section.strip())
    updated = lines[:section["start_index"]] + replacement + lines[section["end_index"]:]
    return "\n".join(updated).strip() + "\n"


def _clean_repaired_section(text: str) -> str:
    value = str(text or "").strip()
    fenced = re.search(r"```(?:markdown|md)?\s*(.*?)\s*```", value, re.DOTALL | re.IGNORECASE)
    if fenced:
        value = fenced.group(1).strip()
    return value


def _section_feedback_by_title(writer_feedback: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        item.get("section_title"): item
        for item in writer_feedback.get("section_feedback") or []
        if item.get("section_title")
    }


def _ledger_items_from_memory(memory: Any) -> List[Dict[str, Any]]:
    if memory is None:
        return []
    ledger = getattr(memory, "evidence_ledger", None)
    if ledger is not None and hasattr(ledger, "to_list"):
        try:
            return list(ledger.to_list())
        except Exception:
            return []
    if isinstance(ledger, list):
        return ledger
    return []


def _normalize_title(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^[一二三四五六七八九十\d]+[、.．]\s*", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def _split_lines(text: str) -> List[str]:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _trim(value: Any, limit: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."
