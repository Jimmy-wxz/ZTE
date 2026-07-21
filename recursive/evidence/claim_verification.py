# coding:utf8

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .graph import (
    DISPLAY_CITATION_RE,
    HEADING_RE,
    REFERENCE_CITATION_RE,
    REFERENCE_HEADING_RE,
    parse_markdown_sections,
)


TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
HIGH_RISK_RE = re.compile(
    r"("
    r"\bROI\b|cost|budget|forecast|market size|growth|CAGR|million|billion|"
    r"CVE-\d{4}-\d+|0day|0-day|zero-day|"
    r"成本|投入|预算|费用|万元|亿元|美元|市场规模|预测|增长率|年均复合|"
    r"漏洞|零日|高危|竞品|竞争|厂商|对标|更高|更低|领先|落后|优于|劣于"
    r")",
    re.IGNORECASE,
)
CONCLUSION_RE = re.compile(
    r"(therefore|thus|shows?|indicates?|means?|suggests?|should|must|"
    r"因此|所以|表明|说明|意味着|建议|必须|应当|需要|关键在于)",
    re.IGNORECASE,
)


def verify_report_claims(
    article: str,
    memory: Any = None,
    ledger_items: Optional[List[Dict[str, Any]]] = None,
    llm_verifier: bool = False,
    verifier_model: Optional[str] = None,
    max_llm_claims: int = 6,
    verifier_client: Any = None,
) -> Dict[str, Any]:
    """Extract and verify report claims against cited evidence.

    This is the low-cost first stage: rules select cited/high-risk claims, then
    lexical overlap and evidence labels produce a conservative verification
    result. A later LLM verifier can keep the same output schema.
    """
    items = ledger_items if ledger_items is not None else _ledger_items_from_memory(memory)
    evidence_by_id = {
        str(item.get("evidence_id")): item
        for item in items
        if item.get("evidence_id")
    }
    evidence_by_global_index = {}
    for item in items:
        global_index = _safe_int(item.get("global_index"))
        if global_index is not None and item.get("evidence_id"):
            evidence_by_global_index[global_index] = str(item.get("evidence_id"))
    evidence_by_display_label = _build_display_label_map(items)

    claims = extract_claims(
        article=article,
        evidence_by_global_index=evidence_by_global_index,
        evidence_by_display_label=evidence_by_display_label,
    )

    verified = [
        _verify_claim(claim, evidence_by_id)
        for claim in claims
    ]
    llm_verifier_result = {
        "enabled": bool(llm_verifier),
        "selected_claim_count": 0,
        "applied_count": 0,
        "error": "",
    }
    if llm_verifier:
        selected = select_claims_for_llm_verification(
            verified, max_claims=max_llm_claims)
        llm_verifier_result["selected_claim_count"] = len(selected)
        if selected:
            try:
                llm_results = _run_llm_verifier(
                    selected,
                    evidence_by_id=evidence_by_id,
                    model=verifier_model,
                    verifier_client=verifier_client,
                )
                applied = _apply_llm_verifier_results(verified, llm_results)
                llm_verifier_result["applied_count"] = applied
            except Exception as exc:
                llm_verifier_result["error"] = str(exc)

    return _build_verification_payload(verified, llm_verifier_result)


def _build_verification_payload(
    verified: List[Dict[str, Any]],
    llm_verifier_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    status_counts = Counter(item["status"] for item in verified)
    risk_counts = Counter(item["risk_level"] for item in verified)
    unsupported = [
        item for item in verified
        if item["status"] == "unsupported"
    ]
    needs_review = [
        item for item in verified
        if item["status"] in ("unsupported", "partially_supported", "needs_review")
    ]

    return {
        "version": "1.0",
        "claims": verified,
        "summary": {
            "claim_count": len(verified),
            "status_counts": dict(status_counts),
            "risk_counts": dict(risk_counts),
            "unsupported_count": len(unsupported),
            "needs_review_count": len(needs_review),
            "cited_claim_count": sum(1 for item in verified if item.get("citations")),
            "high_risk_claim_count": sum(1 for item in verified if item["risk_level"] == "high"),
            "llm_verified_claim_count": sum(1 for item in verified if item.get("verification_source") == "llm"),
        },
        "llm_verifier": llm_verifier_result or {"enabled": False},
        "unsupported_claims": unsupported,
        "needs_review_claims": needs_review[:20],
    }


def select_claims_for_llm_verification(
    claims: List[Dict[str, Any]],
    max_claims: int = 6,
) -> List[Dict[str, Any]]:
    candidates = []
    for claim in claims:
        status = claim.get("status")
        risk_level = claim.get("risk_level")
        if status not in ("unsupported", "partially_supported", "needs_review"):
            continue
        priority = 0
        if risk_level == "high":
            priority += 4
        if status == "unsupported":
            priority += 3
        elif status == "needs_review":
            priority += 2
        else:
            priority += 1
        if claim.get("citations"):
            priority += 1
        candidates.append((priority, claim))
    candidates.sort(key=lambda item: (-item[0], item[1].get("line_number") or 0))
    return [claim for _, claim in candidates[:max(0, int(max_claims or 0))]]


def extract_claims(
    article: str,
    evidence_by_global_index: Optional[Dict[int, str]] = None,
    evidence_by_display_label: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    evidence_by_global_index = evidence_by_global_index or {}
    evidence_by_display_label = evidence_by_display_label or {}
    claims = []
    seen = set()
    for section in parse_markdown_sections(article or ""):
        for line_no, line in _section_lines(section):
            for fragment in _split_claim_fragments(line):
                text = _clean_claim_text(fragment)
                if not text or len(text) < 8:
                    continue
                citations = _extract_citation_refs(
                    fragment,
                    evidence_by_global_index,
                    evidence_by_display_label,
                )
                risk_level, risk_reasons = _risk_profile(text, citations)
                if not citations and risk_level == "low":
                    continue
                key = (section.get("index"), text.lower())
                if key in seen:
                    continue
                seen.add(key)
                claims.append({
                    "claim_id": _claim_id(section.get("index"), text),
                    "section_index": section.get("index"),
                    "section_title": section.get("title"),
                    "line_number": line_no,
                    "text": text,
                    "citations": citations,
                    "risk_level": risk_level,
                    "risk_reasons": risk_reasons,
                })
    return claims


def save_claim_verification(path: str, verification: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(verification, f, indent=2, ensure_ascii=False)


def _verify_claim(claim: Dict[str, Any], evidence_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    citations = claim.get("citations") or []
    if not citations:
        result = dict(claim)
        result.update({
            "status": "unsupported" if claim.get("risk_level") in ("medium", "high") else "unverified",
            "support_score": 0.0,
            "supporting_evidence_ids": [],
            "verification_reason": "No citation attached to this claim.",
            "verification_source": "heuristic",
        })
        return result

    scores = []
    supporting = []
    cited_unknown = []
    for citation in citations:
        evidence_id = citation.get("evidence_id")
        evidence = evidence_by_id.get(evidence_id)
        if not evidence:
            cited_unknown.append(evidence_id or citation.get("label"))
            continue
        score = _claim_evidence_overlap(claim.get("text", ""), evidence)
        label = str(evidence.get("verify_label") or "").lower()
        if label in ("direct_support", "partial_support"):
            score = max(score, 0.45 if label == "direct_support" else 0.32)
        scores.append(score)
        if score >= 0.18 or label in ("direct_support", "partial_support"):
            supporting.append(evidence_id)

    best_score = max(scores) if scores else 0.0
    if supporting and best_score >= 0.38:
        status = "supported"
        reason = "Cited evidence overlaps with the claim and has a supportive evidence label."
    elif supporting or scores:
        status = "partially_supported"
        reason = "The claim has citations, but textual overlap is limited; review may be needed."
    else:
        status = "needs_review"
        reason = "Citations could not be mapped to evidence ledger items."

    result = dict(claim)
    result.update({
        "status": status,
        "support_score": round(best_score, 4),
        "supporting_evidence_ids": supporting,
        "unknown_citations": cited_unknown,
        "verification_reason": reason,
        "verification_source": "heuristic",
    })
    return result


def _run_llm_verifier(
    claims: List[Dict[str, Any]],
    evidence_by_id: Dict[str, Dict[str, Any]],
    model: Optional[str] = None,
    verifier_client: Any = None,
) -> List[Dict[str, Any]]:
    payload = []
    for claim in claims:
        evidence_items = []
        citation_ids = [
            citation.get("evidence_id")
            for citation in claim.get("citations") or []
            if citation.get("evidence_id")
        ]
        for evidence_id in citation_ids[:6]:
            evidence = evidence_by_id.get(evidence_id)
            if not evidence:
                continue
            evidence_items.append({
                "evidence_id": evidence_id,
                "source_type": evidence.get("source_type"),
                "source_title": evidence.get("source_title"),
                "verify_label": evidence.get("verify_label"),
                "text": _trim(evidence.get("chunk_text"), 800),
            })
        payload.append({
            "claim_id": claim.get("claim_id"),
            "claim": claim.get("text"),
            "risk_level": claim.get("risk_level"),
            "heuristic_status": claim.get("status"),
            "evidence": evidence_items,
        })

    if callable(verifier_client):
        return _normalize_llm_verifier_payload(verifier_client(payload))

    if not model:
        raise ValueError("LLM verifier model is required when no verifier_client is provided.")

    from recursive.llm.llm import OpenAIApiProxy

    prompt = """
You are a strict claim verifier for enterprise RAG reports.
Verify each claim only against the provided evidence snippets.

Labels:
- supported: evidence directly supports the claim.
- partially_supported: evidence supports part of the claim but not all details.
- unsupported: evidence does not support the claim, or no evidence is provided.
- contradicted: evidence conflicts with the claim.

Return JSON only, with this shape:
{"results":[{"claim_id":"...","label":"supported|partially_supported|unsupported|contradicted","evidence_ids":["..."],"reason":"...","rewrite_suggestion":"..."}]}

Claims and evidence:
{}
""".strip().format(json.dumps(payload, ensure_ascii=False, indent=2))

    response = OpenAIApiProxy(verbose=False).call(
        model=model,
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        no_cache=True,
        temperature=0.0,
        max_tokens=4096,
    )
    content = response[0]["message"]["content"]
    return _normalize_llm_verifier_payload(_parse_json_object(content))


def _apply_llm_verifier_results(
    claims: List[Dict[str, Any]],
    llm_results: List[Dict[str, Any]],
) -> int:
    by_id = {
        claim.get("claim_id"): claim
        for claim in claims
    }
    applied = 0
    for item in llm_results:
        claim = by_id.get(item.get("claim_id"))
        if not claim:
            continue
        label = str(item.get("label") or "").lower()
        if label not in ("supported", "partially_supported", "unsupported", "contradicted"):
            continue
        claim["llm_label"] = label
        claim["llm_reason"] = item.get("reason", "")
        claim["llm_rewrite_suggestion"] = item.get("rewrite_suggestion", "")
        claim["llm_evidence_ids"] = item.get("evidence_ids") or []
        claim["verification_source"] = "llm"
        if label == "contradicted":
            claim["status"] = "unsupported"
            claim["contradicted"] = True
        elif label == "partially_supported":
            claim["status"] = "partially_supported"
        else:
            claim["status"] = label
        applied += 1
    return applied


def _normalize_llm_verifier_payload(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("results", value.get("claims", []))
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "claim_id": item.get("claim_id"),
            "label": str(item.get("label") or "").lower(),
            "evidence_ids": item.get("evidence_ids") or [],
            "reason": item.get("reason", ""),
            "rewrite_suggestion": item.get("rewrite_suggestion", ""),
        })
    return normalized


def _parse_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        raise


def _section_lines(section: Dict[str, Any]) -> Iterable[Tuple[int, str]]:
    start_line = int(section.get("start_line") or 1)
    for offset, line in enumerate(str(section.get("content") or "").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or HEADING_RE.match(stripped) or TABLE_SEPARATOR_RE.match(stripped):
            continue
        if REFERENCE_HEADING_RE.search(stripped):
            continue
        yield start_line + offset, stripped


def _split_claim_fragments(line: str) -> List[str]:
    text = str(line or "").strip()
    if "|" in text and text.count("|") >= 2:
        return [cell.strip() for cell in text.strip("|").split("|") if cell.strip()]
    parts = re.split(r"(?<=[。！？!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _clean_claim_text(text: str) -> str:
    text = str(text or "").strip()
    text = re.sub(r"^[>\-\*\d\.\s]+", "", text)
    text = REFERENCE_CITATION_RE.sub("", text)
    text = DISPLAY_CITATION_RE.sub("", text)
    text = re.sub(r"\]\([^)]+\)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" |")


def _extract_citation_refs(
    text: str,
    evidence_by_global_index: Dict[int, str],
    evidence_by_display_label: Dict[str, str],
) -> List[Dict[str, Any]]:
    refs = []
    seen = set()
    for match in REFERENCE_CITATION_RE.finditer(text or ""):
        label = "reference:{}".format(match.group(1))
        evidence_id = evidence_by_global_index.get(_safe_int(match.group(1)))
        key = (label, evidence_id)
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            "label": label,
            "evidence_id": evidence_id,
        })

    for match in DISPLAY_CITATION_RE.finditer(text or ""):
        label = "{}:{}".format(match.group(1).upper(), match.group(2))
        evidence_id = evidence_by_display_label.get(label)
        key = (label, evidence_id)
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            "label": label,
            "evidence_id": evidence_id,
        })
    return refs


def _risk_profile(text: str, citations: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    reasons = []
    if HIGH_RISK_RE.search(text):
        reasons.append("high_risk_topic")
    if re.search(r"\d", text):
        reasons.append("numeric_claim")
    if CONCLUSION_RE.search(text):
        reasons.append("conclusion_or_recommendation")
    if citations:
        reasons.append("cited_claim")

    if "high_risk_topic" in reasons or ("numeric_claim" in reasons and not citations):
        return "high", reasons
    if "numeric_claim" in reasons or "conclusion_or_recommendation" in reasons or citations:
        return "medium", reasons
    return "low", reasons


def _claim_evidence_overlap(claim_text: str, evidence: Dict[str, Any]) -> float:
    claim_terms = _terms(claim_text)
    if not claim_terms:
        return 0.0
    evidence_text = "{}\n{}\n{}\n{}".format(
        evidence.get("source_title", ""),
        evidence.get("source_uri", ""),
        evidence.get("chunk_text", ""),
        " ".join(evidence.get("supported_facts") or []),
    )
    evidence_terms = set(_terms(evidence_text))
    if not evidence_terms:
        return 0.0
    hits = [term for term in claim_terms if term in evidence_terms]
    return len(hits) / max(1, min(len(claim_terms), 24))


def _terms(text: str) -> List[str]:
    raw = str(text or "")
    terms = []
    for item in re.findall(r"\b[A-Z]{2,12}\b", raw):
        terms.append(item.lower())
    for item in re.findall(r"\b[A-Za-z][A-Za-z0-9_\-]{1,}\b", raw):
        terms.append(item.lower())
    for span in re.findall(r"[\u4e00-\u9fff]{2,}", raw):
        for size in (2, 3, 4):
            for idx in range(max(0, len(span) - size + 1)):
                terms.append(span[idx:idx + size])
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "into",
        "report", "analysis", "should", "would", "could", "therefore",
        "进行", "相关", "包括", "报告", "分析", "建议", "需要",
    }
    result = []
    seen = set()
    for term in terms:
        term = term.strip().lower()
        if len(term) < 2 or term in stop or term in seen:
            continue
        seen.add(term)
        result.append(term)
    return result[:48]


def _build_display_label_map(items: List[Dict[str, Any]]) -> Dict[str, str]:
    mapping = {}
    counters = defaultdict(int)
    sorted_items = sorted(
        [item for item in items if item.get("evidence_id")],
        key=lambda item: (_safe_int(item.get("global_index")) is None, _safe_int(item.get("global_index")) or 0),
    )
    for item in sorted_items:
        source_type = str(item.get("source_type") or "unknown").lower()
        if source_type not in ("kb", "web"):
            continue
        counters[source_type] += 1
        mapping["{}:{}".format(source_type.upper(), counters[source_type])] = str(item.get("evidence_id"))
    return mapping


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


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _claim_id(section_index: Any, text: str) -> str:
    payload = "{}\n{}".format(section_index, text)
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:16]
