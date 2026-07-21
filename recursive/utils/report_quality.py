# coding:utf8

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
REFERENCE_HEADING_RE = re.compile(r"(references|参考资料|参考文献)", re.IGNORECASE)
EXECUTIVE_SUMMARY_RE = re.compile(r"^(执行摘要|executive summary|管理摘要)\b", re.IGNORECASE)
CITATION_RE = re.compile(r"\[(?:reference|ref):\d+\]|\[KB:\d+\]|\[WEB:\d+\]", re.IGNORECASE)
AUDIT_HEADING_RE = re.compile(r"^\s*#{1,6}\s+证据审计提示\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")

QUANTITATIVE_SIGNAL_RE = re.compile(
    r"("
    r"\bROI\b|投资回报|回报率|成本|投入|预算|费用|万元|亿元|美元|人民币|"
    r"市场规模|预测|增长率|CAGR|年均复合|百分比|%|"
    r"\bCVE-\d{4}-\d+\b|0day|0-day|零日|漏洞编号|"
    r"\$|USD|RMB|million|billion|cost|budget|forecast|growth"
    r")",
    re.IGNORECASE,
)
ESTIMATE_QUALIFIER_RE = re.compile(
    r"(估算|预估|假设|需复核|需验证|未检索到直接来源|基于行业经验|"
    r"estimate|estimated|assumption|needs validation|not directly sourced)",
    re.IGNORECASE,
)


def postprocess_report_quality(markdown: str, add_audit_section: bool = True) -> Tuple[str, Dict[str, Any]]:
    """Apply deterministic report-quality fixes and return an audit payload.

    The function deliberately avoids LLM calls. It performs layout repair
    (executive summary placement) and surfaces grounding risks that prompts
    alone cannot reliably eliminate, especially unsupported numeric estimates.
    """
    original = str(markdown or "")
    moved_text, moved_summary = move_executive_summary_to_front(original)
    audit = audit_report_quality(moved_text)
    audit["executive_summary_moved"] = moved_summary

    if add_audit_section:
        moved_text = insert_grounding_audit_section(moved_text, audit)
    return moved_text, audit


def save_report_quality_audit(path: str, audit: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)


def move_executive_summary_to_front(markdown: str) -> Tuple[str, bool]:
    lines = _split_lines(markdown)
    block = _find_heading_block(lines, EXECUTIVE_SUMMARY_RE)
    if block is None:
        return markdown, False

    start, end = block
    insert_at = _front_insert_index(lines)
    if start <= insert_at <= end:
        return markdown, False

    summary_lines = _trim_blank_edges(lines[start:end])
    remaining = lines[:start] + lines[end:]
    if insert_at > start:
        insert_at -= end - start
    remaining = _insert_block(remaining, insert_at, summary_lines)
    return "\n".join(remaining).strip() + "\n", True


def audit_report_quality(markdown: str) -> Dict[str, Any]:
    body_lines = _lines_before_references(_split_lines(markdown))
    unsupported = _find_unsupported_quantitative_claims(body_lines)
    section_metrics = _section_citation_metrics(body_lines)
    low_citation_sections = [
        item for item in section_metrics
        if item["char_count"] >= 220 and item["citation_count"] < 2
    ]

    return {
        "unsupported_quantitative_claims": unsupported,
        "unsupported_quantitative_count": len(unsupported),
        "low_citation_sections": low_citation_sections,
        "low_citation_section_count": len(low_citation_sections),
        "section_citation_metrics": section_metrics,
    }


def insert_grounding_audit_section(markdown: str, audit: Dict[str, Any]) -> str:
    if not audit.get("unsupported_quantitative_claims"):
        return markdown
    if AUDIT_HEADING_RE.search(markdown or ""):
        return markdown

    warning_lines = [
        "## 证据审计提示",
        "",
        "以下定量或安全事件相关表述未检测到直接引用，建议在正式提交前补充来源，或将其明确标注为估算：",
        "",
    ]
    for item in audit.get("unsupported_quantitative_claims", [])[:8]:
        warning_lines.append("- 第 {} 行：{}".format(item["line_number"], item["text"]))
    warning_lines.append("")

    lines = _split_lines(markdown)
    ref_index = _reference_heading_index(lines)
    if ref_index is None:
        return markdown.rstrip() + "\n\n" + "\n".join(warning_lines)
    prefix = lines[:ref_index]
    suffix = lines[ref_index:]
    return "\n".join(_trim_trailing_blank(prefix) + [""] + warning_lines + suffix).strip() + "\n"


def _find_unsupported_quantitative_claims(lines: List[str]) -> List[Dict[str, Any]]:
    findings = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or TABLE_SEPARATOR_RE.match(stripped):
            continue
        if not QUANTITATIVE_SIGNAL_RE.search(stripped):
            continue
        if not _contains_digit_or_cve(stripped):
            continue
        if CITATION_RE.search(stripped) or ESTIMATE_QUALIFIER_RE.search(stripped):
            continue
        findings.append({
            "line_number": idx,
            "text": _trim(stripped, 220),
            "signal": QUANTITATIVE_SIGNAL_RE.search(stripped).group(0),
        })
    return findings


def _section_citation_metrics(lines: List[str]) -> List[Dict[str, Any]]:
    sections = []
    current = {
        "title": "Document body",
        "level": 0,
        "start_line": 1,
        "content": [],
    }

    for idx, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line.strip())
        if match:
            _finish_section_metrics(sections, current, idx - 1)
            current = {
                "title": match.group(2).strip(),
                "level": len(match.group(1)),
                "start_line": idx,
                "content": [],
            }
            continue
        current["content"].append(line)
    _finish_section_metrics(sections, current, len(lines))
    return [section for section in sections if section["char_count"] > 0]


def _finish_section_metrics(sections: List[Dict[str, Any]], current: Dict[str, Any], end_line: int) -> None:
    content = "\n".join(current.get("content") or []).strip()
    if not content:
        return
    sections.append({
        "title": current.get("title") or "Untitled",
        "level": current.get("level", 0),
        "start_line": current.get("start_line", 1),
        "end_line": end_line,
        "char_count": len(content),
        "citation_count": len(CITATION_RE.findall(content)),
    })


def _find_heading_block(lines: List[str], title_pattern: re.Pattern) -> Optional[Tuple[int, int]]:
    for idx, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        title = match.group(2).strip()
        if not title_pattern.search(title):
            continue
        level = len(match.group(1))
        end = len(lines)
        for next_idx in range(idx + 1, len(lines)):
            next_match = HEADING_RE.match(lines[next_idx].strip())
            if next_match and len(next_match.group(1)) <= level:
                end = next_idx
                break
        return idx, end
    return None


def _front_insert_index(lines: List[str]) -> int:
    for idx, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if match and len(match.group(1)) == 1:
            insert_at = idx + 1
            while insert_at < len(lines) and not lines[insert_at].strip():
                insert_at += 1
            return insert_at
    return 0


def _reference_heading_index(lines: List[str]) -> Optional[int]:
    for idx, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if match and REFERENCE_HEADING_RE.search(match.group(2).strip()):
            return idx
    return None


def _lines_before_references(lines: List[str]) -> List[str]:
    ref_idx = _reference_heading_index(lines)
    return lines if ref_idx is None else lines[:ref_idx]


def _insert_block(lines: List[str], index: int, block: List[str]) -> List[str]:
    prefix = _trim_trailing_blank(lines[:index])
    suffix = _trim_leading_blank(lines[index:])
    if prefix:
        prefix.append("")
    return prefix + block + [""] + suffix


def _trim_blank_edges(lines: List[str]) -> List[str]:
    return _trim_leading_blank(_trim_trailing_blank(lines))


def _trim_leading_blank(lines: List[str]) -> List[str]:
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    return lines[idx:]


def _trim_trailing_blank(lines: List[str]) -> List[str]:
    idx = len(lines)
    while idx > 0 and not lines[idx - 1].strip():
        idx -= 1
    return lines[:idx]


def _split_lines(markdown: str) -> List[str]:
    return str(markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _contains_digit_or_cve(text: str) -> bool:
    return bool(re.search(r"\d|CVE-\d{4}-\d+", text, re.IGNORECASE))


def _trim(value: Any, limit: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."
