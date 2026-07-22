# coding:utf8

import re
from typing import Any, Dict, List


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
REFERENCE_HEADING_RE = re.compile(r"(references|参考资料|参考文献)", re.IGNORECASE)


def parse_report_sections(report: str) -> List[Dict[str, Any]]:
    """Parse editable Markdown sections, excluding references."""
    lines = _split_lines(report)
    sections: List[Dict[str, Any]] = []
    current = None

    for index, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        title = match.group(2).strip()
        if REFERENCE_HEADING_RE.search(title):
            if current:
                current["end_index"] = index
                current["end_line"] = index
                current["markdown"] = "\n".join(
                    lines[current["start_index"]:current["end_index"]]).strip()
                sections.append(current)
            current = None
            break
        if current:
            current["end_index"] = index
            current["end_line"] = index
            current["markdown"] = "\n".join(
                lines[current["start_index"]:current["end_index"]]).strip()
            sections.append(current)
        current = {
            "index": len(sections),
            "level": len(match.group(1)),
            "title": title,
            "start_index": index,
            "start_line": index + 1,
            "end_index": len(lines),
            "end_line": len(lines),
            "markdown": "",
        }

    if current:
        current["markdown"] = "\n".join(
            lines[current["start_index"]:current["end_index"]]).strip()
        sections.append(current)

    if not sections and str(report or "").strip():
        sections.append({
            "index": 0,
            "level": 0,
            "title": "Document body",
            "start_index": 0,
            "start_line": 1,
            "end_index": len(lines),
            "end_line": len(lines),
            "markdown": str(report or "").strip(),
        })
    return sections


def find_target_sections(
    report: str,
    instruction: str,
    intent: Dict[str, Any] = None,
    max_sections: int = 1,
) -> List[Dict[str, Any]]:
    intent = intent or {}
    sections = parse_report_sections(report)
    if not sections:
        return []
    if intent.get("scope") == "full_report":
        return [_full_report_section(report)]

    hint = intent.get("target_section_hint") or ""
    if hint:
        matched = _rank_sections(sections, hint)
        if matched:
            return matched[:max(1, int(max_sections or 1))]

    matched = _rank_sections(sections, instruction)
    if matched and matched[0].get("score", 0) > 0:
        return matched[:max(1, int(max_sections or 1))]

    if intent.get("scope") == "evidence_sensitive":
        risk_ranked = _rank_sections(
            sections,
            "ROI cost budget market size CVE 0day 成本 投入 预算 市场规模 漏洞",
            include_body=True,
        )
        if risk_ranked and risk_ranked[0].get("score", 0) > 0:
            return risk_ranked[:max(1, int(max_sections or 1))]

    return [sections[0]]


def replace_section(report: str, section: Dict[str, Any], replacement: str) -> str:
    value = str(replacement or "").strip()
    if not value:
        return report
    if section.get("full_report"):
        return value.strip() + "\n"
    lines = _split_lines(report)
    new_lines = _split_lines(value)
    updated = lines[:section["start_index"]] + new_lines + lines[section["end_index"]:]
    return "\n".join(updated).strip() + "\n"


def _rank_sections(
    sections: List[Dict[str, Any]],
    query: str,
    include_body: bool = False,
) -> List[Dict[str, Any]]:
    terms = _terms(query)
    if not terms:
        return []
    ranked = []
    for section in sections:
        haystack = section.get("title", "")
        if include_body:
            haystack += "\n" + section.get("markdown", "")
        norm = _normalize(haystack)
        score = sum(1 for term in terms if term in norm)
        if score <= 0:
            continue
        item = dict(section)
        item["score"] = score
        ranked.append(item)
    return sorted(ranked, key=lambda item: (-item.get("score", 0), item.get("index", 0)))


def _full_report_section(report: str) -> Dict[str, Any]:
    lines = _split_lines(report)
    return {
        "index": -1,
        "level": 0,
        "title": "Full report",
        "start_index": 0,
        "start_line": 1,
        "end_index": len(lines),
        "end_line": len(lines),
        "markdown": str(report or "").strip(),
        "full_report": True,
    }


def _terms(value: str) -> List[str]:
    normalized = _normalize(value)
    terms = []
    terms.extend(re.findall(r"[a-z][a-z0-9_\-]{2,}", normalized))
    for span in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        if len(span) <= 6:
            terms.append(span)
        else:
            for idx in range(0, len(span) - 1):
                terms.append(span[idx:idx + 2])
    seen = set()
    result = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        result.append(term)
    return result[:24]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _split_lines(text: str) -> List[str]:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
