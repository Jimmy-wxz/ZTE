# coding:utf8

import hashlib
import math
import re
import threading
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


SUPPORT_LABELS = {
    "direct_support",
    "partial_support",
}


@dataclass
class EvidenceUnit:
    evidence_id: str
    node_id: str
    node_goal: str
    sub_question: str
    source_type: str
    source_uri: str
    source_title: str
    chunk_text: str
    retrieval_score: float = 0.0
    rerank_score: float = 0.0
    verify_label: str = "unverified"
    verify_score: float = 0.0
    supported_facts: List[str] = field(default_factory=list)
    reason: str = ""
    used_in_section: str = ""
    citation_label: str = ""
    global_index: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _sha1_short(parts: Iterable[str], length: int = 16) -> str:
    payload = "\n".join(_clean_text(p) for p in parts)
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:length]


def _source_type_from_page(page: Dict[str, Any], fallback: str = "") -> str:
    url = _clean_text(page.get("url"))
    if url.startswith(("local-kb://", "kb://")):
        return "kb"
    if fallback:
        return fallback
    return "web"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except Exception:
        return default


def _normalize_rerank_score(score: float) -> float:
    # bge-reranker scores often live in a wider logit-like range. Fast mode
    # already writes scores in [0, 1]. Keep this monotonic and deterministic.
    if 0.0 <= score <= 1.0:
        return score
    return 1.0 / (1.0 + math.exp(-score))


def _terms(text: str) -> List[str]:
    text = _clean_text(text)
    if not text:
        return []

    english = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", text.lower())
    acronyms = [m.lower() for m in re.findall(r"\b[A-Z]{2,8}\b", text)]

    # For Chinese text, long contiguous spans are too coarse. Use a compact set
    # of overlapping bigrams/trigrams so the heuristic verifier can still spot
    # evidence overlap without external tokenizers.
    chinese_terms = []
    for span in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        span = span[:40]
        for size in (2, 3):
            for idx in range(max(0, len(span) - size + 1)):
                chinese_terms.append(span[idx:idx + size])

    stop_terms = {
        "the", "and", "for", "with", "from", "that", "this", "into",
        "report", "market", "analysis", "技术", "市场", "分析", "报告",
        "进行", "相关", "包括", "需要", "形成",
    }
    terms = []
    seen = set()
    for term in acronyms + english + chinese_terms:
        term = term.strip().lower()
        if len(term) < 2 or term in stop_terms or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _term_overlap_score(question: str, text: str) -> Tuple[float, List[str]]:
    question_terms = _terms(question)
    if not question_terms:
        return 0.0, []
    text_lower = _clean_text(text).lower()
    hits = [term for term in question_terms if term in text_lower]
    return len(hits) / max(1, min(len(question_terms), 24)), hits[:8]


def verify_page_evidence(
    sub_question: str,
    page: Dict[str, Any],
    mode: str = "heuristic",
) -> Dict[str, Any]:
    """Return a lightweight evidence-verification judgment for a retrieved page.

    The default verifier is deterministic and intentionally cheap. It gives the
    project an auditable evidence layer without adding another LLM call to the
    critical path. Future LLM verifier implementations can keep this schema.
    """
    mode = (mode or "heuristic").lower()
    if mode in ("0", "false", "off", "none", "disabled"):
        return {
            "verify_label": "unverified",
            "verify_score": 0.0,
            "supported_facts": [],
            "reason": "Evidence verification disabled.",
        }

    summary = _clean_text(page.get("summary") or page.get("content") or page.get("snippet"))
    title = _clean_text(page.get("title"))
    overlap, hits = _term_overlap_score(sub_question, "{}\n{}".format(title, summary))
    rerank_score = _normalize_rerank_score(_safe_float(page.get("rerank_score"), 0.0))
    fast_score = min(1.0, max(0.0, _safe_float(page.get("fast_kb_score"), 0.0) / 10.0))
    source_quality = min(1.0, max(0.0, (_safe_float(page.get("source_quality_score"), 0.0) + 2.0) / 5.0))

    verify_score = max(
        overlap,
        0.65 * rerank_score + 0.35 * overlap,
        0.55 * fast_score + 0.45 * overlap,
        0.45 * source_quality + 0.55 * overlap,
    )
    verify_score = round(min(1.0, max(0.0, verify_score)), 4)

    if verify_score >= 0.72 and overlap >= 0.12:
        label = "direct_support"
    elif verify_score >= 0.45 or overlap >= 0.18:
        label = "partial_support"
    elif overlap > 0.0:
        label = "background"
    else:
        label = "irrelevant"

    reason = "heuristic overlap={:.2f}, rerank={:.2f}, terms={}".format(
        overlap, rerank_score, ", ".join(hits) if hits else "none"
    )
    return {
        "verify_label": label,
        "verify_score": verify_score,
        "supported_facts": hits,
        "reason": reason,
    }


def build_evidence_unit(
    page: Dict[str, Any],
    node_id: str,
    node_goal: str,
    sub_question: Optional[str] = None,
    source_type: str = "",
    verify_mode: str = "heuristic",
) -> EvidenceUnit:
    source_type = _source_type_from_page(page, source_type)
    source_uri = _clean_text(page.get("url") or page.get("source"))
    source_title = _clean_text(page.get("title") or page.get("source") or "Untitled")
    chunk_text = _clean_text(page.get("summary") or page.get("content") or page.get("snippet"))
    sub_question = _clean_text(sub_question or node_goal)
    evidence_id = _sha1_short([
        node_id,
        sub_question,
        source_type,
        source_uri,
        chunk_text[:500],
    ])
    verification = verify_page_evidence(sub_question, page, mode=verify_mode)
    global_index = page.get("global_index")
    citation_label = "[reference:{}]".format(global_index) if global_index else ""

    return EvidenceUnit(
        evidence_id=evidence_id,
        node_id=_clean_text(node_id),
        node_goal=_clean_text(node_goal),
        sub_question=sub_question,
        source_type=source_type,
        source_uri=source_uri,
        source_title=source_title,
        chunk_text=chunk_text,
        retrieval_score=_safe_float(page.get("distance"), 0.0),
        rerank_score=_safe_float(page.get("rerank_score"), 0.0),
        verify_label=verification["verify_label"],
        verify_score=verification["verify_score"],
        supported_facts=verification["supported_facts"],
        reason=verification["reason"],
        citation_label=citation_label,
        global_index=global_index if isinstance(global_index, int) else None,
        metadata={
            "search_query": page.get("search_query", ""),
            "pk_index": page.get("pk_index"),
            "fast_kb_score": page.get("fast_kb_score"),
            "source_quality_score": page.get("source_quality_score"),
        },
    )


def annotate_page_evidence(
    page: Dict[str, Any],
    node_id: str,
    node_goal: str,
    sub_question: Optional[str] = None,
    source_type: str = "",
    verify_mode: str = "heuristic",
) -> Dict[str, Any]:
    evidence = build_evidence_unit(
        page=page,
        node_id=node_id,
        node_goal=node_goal,
        sub_question=sub_question,
        source_type=source_type,
        verify_mode=verify_mode,
    )
    page["evidence_id"] = evidence.evidence_id
    page["evidence"] = evidence.to_dict()
    return page


class EvidenceLedger:
    def __init__(self):
        self._items: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def add(self, evidence: EvidenceUnit) -> Dict[str, Any]:
        with self._lock:
            item = evidence.to_dict()
            self._items[evidence.evidence_id] = item
            return item

    def register_page(self, page: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        evidence = page.get("evidence")
        if not evidence:
            return None
        item = deepcopy(evidence)
        global_index = page.get("global_index")
        item["global_index"] = global_index
        if global_index:
            item["citation_label"] = "[reference:{}]".format(global_index)
        page["evidence"] = item
        page["evidence_id"] = item.get("evidence_id")
        with self._lock:
            self._items[item["evidence_id"]] = item
        return item

    def to_list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._items.values())

    def supported(self) -> List[Dict[str, Any]]:
        return [
            item for item in self.to_list()
            if item.get("verify_label") in SUPPORT_LABELS
        ]
