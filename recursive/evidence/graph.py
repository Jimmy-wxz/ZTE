# coding:utf8

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


REFERENCE_CITATION_RE = re.compile(r"\[reference:(\d+)\]", re.IGNORECASE)
DISPLAY_CITATION_RE = re.compile(r"\[\[?(KB|WEB):(\d+)\]?\]", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
REFERENCE_HEADING_RE = re.compile(r"(references|参考资料|参考文献)", re.IGNORECASE)


@dataclass
class GraphNode:
    id: str
    type: str
    label: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraphEdge:
    source: str
    target: str
    type: str
    weight: float = 1.0
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceGraph:
    """A lightweight audit graph linking report sections, claims, evidence and rubric dimensions."""

    def __init__(self):
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[Tuple[str, str, str], GraphEdge] = {}
        self.summary: Dict[str, Any] = {}

    def add_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> GraphNode:
        payload = payload or {}
        if node_id in self._nodes:
            existing = self._nodes[node_id]
            existing.payload.update({k: v for k, v in payload.items() if v not in (None, "", [], {})})
            if label and not existing.label:
                existing.label = label
            return existing

        node = GraphNode(
            id=node_id,
            type=node_type,
            label=_trim(label, 160),
            payload=_jsonable(payload),
        )
        self._nodes[node_id] = node
        return node

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        weight: float = 1.0,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[GraphEdge]:
        if not source or not target:
            return None
        key = (source, target, edge_type)
        payload = payload or {}
        if key in self._edges:
            edge = self._edges[key]
            edge.weight = max(edge.weight, weight)
            edge.payload.update({k: v for k, v in payload.items() if v not in (None, "", [], {})})
            return edge

        edge = GraphEdge(
            source=source,
            target=target,
            type=edge_type,
            weight=round(float(weight or 1.0), 4),
            payload=_jsonable(payload),
        )
        self._edges[key] = edge
        return edge

    @property
    def nodes(self) -> List[Dict[str, Any]]:
        return [node.to_dict() for node in self._nodes.values()]

    @property
    def edges(self) -> List[Dict[str, Any]]:
        return [edge.to_dict() for edge in self._edges.values()]

    def to_dict(self) -> Dict[str, Any]:
        summary = dict(self.summary)
        node_types = Counter(node.type for node in self._nodes.values())
        edge_types = Counter(edge.type for edge in self._edges.values())
        summary.update({
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "node_types": dict(node_types),
            "edge_types": dict(edge_types),
        })
        return {
            "version": "1.0",
            "nodes": self.nodes,
            "edges": self.edges,
            "summary": summary,
        }


def build_evidence_graph(
    memory: Any = None,
    article: str = "",
    root_node_json: Optional[Dict[str, Any]] = None,
    ledger_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build an auditable evidence graph without adding LLM calls."""
    graph = EvidenceGraph()
    graph.add_node("document:report", "document", "Generated report", {})

    items = ledger_items if ledger_items is not None else _ledger_items_from_memory(memory)
    evidence_by_id: Dict[str, Dict[str, Any]] = {}
    evidence_by_global_index: Dict[int, str] = {}
    evidence_to_cluster_id: Dict[str, str] = {}
    cluster_counts = defaultdict(int)
    evidence_by_display_label = _build_display_label_map(items)
    rubric_dimensions_by_evidence = _rubric_dimensions_by_evidence(root_node_json or {})

    for item in items:
        evidence_id = _clean(item.get("evidence_id"))
        if not evidence_id:
            continue
        evidence_node_id = _evidence_node_id(evidence_id)
        evidence_by_id[evidence_id] = item
        global_index = _safe_int(item.get("global_index"))
        if global_index is not None:
            evidence_by_global_index[global_index] = evidence_id

        source_type = _clean(item.get("source_type") or "unknown").lower()
        source_uri = _clean(item.get("source_uri") or item.get("source") or item.get("url"))
        source_title = _clean(item.get("source_title") or source_uri or "Unknown source")
        source_node_id = _source_node_id(source_uri or source_title)
        task_node_id = _task_node_id(item.get("node_id") or "unknown")
        cluster_node_id = _cluster_node_id(source_type, source_uri or source_title)
        evidence_to_cluster_id[evidence_id] = cluster_node_id
        cluster_counts[cluster_node_id] += 1

        graph.add_node(task_node_id, "task", item.get("node_goal") or item.get("sub_question") or "Retrieval task", {
            "node_id": item.get("node_id"),
            "goal": item.get("node_goal"),
            "sub_question": item.get("sub_question"),
        })
        graph.add_node(source_node_id, "source", source_title, {
            "source_type": source_type,
            "uri": source_uri,
            "title": source_title,
        })
        graph.add_node(cluster_node_id, "evidence_cluster", "{} evidence: {}".format(source_type.upper(), source_title), {
            "source_type": source_type,
            "source_uri": source_uri,
            "source_title": source_title,
        })
        graph.add_node(evidence_node_id, "evidence", source_title, {
            "evidence_id": evidence_id,
            "source_type": source_type,
            "source_uri": source_uri,
            "source_title": source_title,
            "global_index": global_index,
            "citation_label": item.get("citation_label"),
            "verify_label": item.get("verify_label"),
            "verify_score": item.get("verify_score"),
            "retrieval_score": item.get("retrieval_score"),
            "rerank_score": item.get("rerank_score"),
            "supported_facts": item.get("supported_facts") or [],
            "reason": item.get("reason"),
            "preview": _trim(item.get("chunk_text"), 320),
            "metadata": item.get("metadata") or {},
        })
        graph.add_edge(task_node_id, evidence_node_id, "retrieved", _safe_float(item.get("verify_score"), 0.0), {
            "citation_label": item.get("citation_label"),
        })
        graph.add_edge(evidence_node_id, source_node_id, "from_source", 1.0, {
            "source_type": source_type,
        })
        graph.add_edge(cluster_node_id, evidence_node_id, "contains_evidence", 1.0, {})
        graph.add_edge(cluster_node_id, source_node_id, "grounded_in_source", 1.0, {
            "source_type": source_type,
        })

    for cluster_id, count in cluster_counts.items():
        if cluster_id in graph._nodes:
            graph._nodes[cluster_id].payload["evidence_count"] = count

    cited_evidence_ids: Set[str] = set()
    claim_count, section_evidence_map = _add_article_sections(
        graph=graph,
        article=article or "",
        evidence_by_global_index=evidence_by_global_index,
        evidence_by_display_label=evidence_by_display_label,
        evidence_by_id=evidence_by_id,
        evidence_to_cluster_id=evidence_to_cluster_id,
        rubric_dimensions_by_evidence=rubric_dimensions_by_evidence,
        cited_evidence_ids=cited_evidence_ids,
    )
    rubric_summary = _add_rubric_nodes(graph, root_node_json or {}, evidence_by_id)

    source_type_counts = Counter(
        _clean(item.get("source_type") or "unknown").lower()
        for item in items
        if item.get("evidence_id")
    )
    graph.summary.update({
        "evidence_total": len(evidence_by_id),
        "cited_evidence": len(cited_evidence_ids),
        "uncited_evidence": max(0, len(evidence_by_id) - len(cited_evidence_ids)),
        "claim_count": claim_count,
        "source_type_counts": dict(source_type_counts),
        "rubric_dimension_count": rubric_summary["dimension_count"],
        "rubric_missing": rubric_summary["missing"],
        "evidence_cluster_count": len(cluster_counts),
        "section_evidence_map": section_evidence_map,
    })
    return graph.to_dict()


def save_evidence_graph(path: str, graph_data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2, ensure_ascii=False)


def parse_markdown_sections(article: str) -> List[Dict[str, Any]]:
    lines = (article or "").splitlines()
    sections: List[Dict[str, Any]] = []
    current = {
        "index": 0,
        "level": 0,
        "title": "Document body",
        "start_line": 1,
        "lines": [],
    }

    for line_number, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line.strip())
        if match:
            title = match.group(2).strip().strip("#").strip()
            if REFERENCE_HEADING_RE.match(title):
                _finish_section(current, sections, line_number - 1)
                current = None
                break
            _finish_section(current, sections, line_number - 1)
            current = {
                "index": len(sections),
                "level": len(match.group(1)),
                "title": title,
                "start_line": line_number,
                "lines": [],
            }
        else:
            current["lines"].append(line)

    if current is not None:
        _finish_section(current, sections, len(lines))

    if not sections and article.strip():
        sections.append({
            "index": 0,
            "level": 0,
            "title": "Document body",
            "start_line": 1,
            "end_line": len(lines),
            "content": article,
        })
    return sections


def _finish_section(current: Dict[str, Any], sections: List[Dict[str, Any]], end_line: int) -> None:
    content = "\n".join(current.get("lines") or []).strip()
    if not content and current.get("level", 0) == 0:
        return
    current["end_line"] = max(current.get("start_line", 1), end_line)
    current["content"] = content
    current.pop("lines", None)
    current["index"] = len(sections)
    sections.append(current)


def _add_article_sections(
    graph: EvidenceGraph,
    article: str,
    evidence_by_global_index: Dict[int, str],
    evidence_by_display_label: Dict[str, str],
    evidence_by_id: Dict[str, Dict[str, Any]],
    evidence_to_cluster_id: Dict[str, str],
    rubric_dimensions_by_evidence: Dict[str, List[str]],
    cited_evidence_ids: Set[str],
) -> Tuple[int, List[Dict[str, Any]]]:
    sections = parse_markdown_sections(article)
    claim_count = 0
    section_evidence_map = []
    for section in sections:
        section_id = _section_node_id(section["index"], section.get("title"))
        graph.add_node(section_id, "section", section.get("title") or "Untitled section", {
            "index": section.get("index"),
            "level": section.get("level"),
            "start_line": section.get("start_line"),
            "end_line": section.get("end_line"),
        })
        graph.add_edge("document:report", section_id, "has_section", 1.0, {
            "order": section.get("index"),
        })

        citations = _citation_evidence_ids(
            section.get("content", ""),
            evidence_by_global_index,
            evidence_by_display_label,
        )
        cluster_ids = []
        source_type_counts = Counter()
        rubric_dimensions = set()
        for evidence_id in citations:
            cited_evidence_ids.add(evidence_id)
            graph.add_edge(section_id, _evidence_node_id(evidence_id), "cites", 1.0, {})
            cluster_id = evidence_to_cluster_id.get(evidence_id)
            if cluster_id and cluster_id not in cluster_ids:
                cluster_ids.append(cluster_id)
                graph.add_edge(section_id, cluster_id, "uses_evidence_cluster", 1.0, {})
            source_type = _clean((evidence_by_id.get(evidence_id) or {}).get("source_type") or "unknown").lower()
            source_type_counts[source_type] += 1
            rubric_dimensions.update(rubric_dimensions_by_evidence.get(evidence_id, []))

        map_node_id = _section_map_node_id(section_id)
        map_payload = {
            "section_id": section_id,
            "section_index": section.get("index"),
            "section_title": section.get("title"),
            "start_line": section.get("start_line"),
            "end_line": section.get("end_line"),
            "citation_count": len(citations),
            "evidence_ids": citations,
            "cluster_ids": cluster_ids,
            "kb_evidence_count": source_type_counts.get("kb", 0),
            "web_evidence_count": source_type_counts.get("web", 0),
            "rubric_dimensions": sorted(rubric_dimensions),
        }
        graph.add_node(map_node_id, "section_evidence_map", "Evidence map: {}".format(section.get("title") or "Untitled section"), map_payload)
        graph.add_edge(section_id, map_node_id, "has_evidence_map", 1.0, {})
        for evidence_id in citations:
            graph.add_edge(map_node_id, _evidence_node_id(evidence_id), "maps_evidence", 1.0, {})
        for cluster_id in cluster_ids:
            graph.add_edge(map_node_id, cluster_id, "maps_cluster", 1.0, {})
        section_evidence_map.append(map_payload)

        for claim in _extract_cited_claims(section.get("content", "")):
            claim_citations = _citation_evidence_ids(
                claim,
                evidence_by_global_index,
                evidence_by_display_label,
            )
            if not claim_citations:
                continue
            clean_claim = _strip_citations(claim)
            if not clean_claim:
                continue
            claim_id = _claim_node_id(section_id, clean_claim)
            graph.add_node(claim_id, "claim", clean_claim, {
                "section_id": section_id,
                "text": clean_claim,
            })
            graph.add_edge(section_id, claim_id, "contains_claim", 1.0, {})
            for evidence_id in claim_citations:
                cited_evidence_ids.add(evidence_id)
                graph.add_edge(claim_id, _evidence_node_id(evidence_id), "supported_by", 1.0, {})
            claim_count += 1
    return claim_count, section_evidence_map


def _add_rubric_nodes(
    graph: EvidenceGraph,
    root_node_json: Dict[str, Any],
    evidence_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    seen_dimensions: Set[str] = set()
    missing: Set[str] = set()
    for gap in _iter_rubric_gaps(root_node_json):
        for dimension in gap.get("dimensions") or []:
            dimension_id = _clean(dimension.get("dimension_id"))
            if not dimension_id:
                continue
            seen_dimensions.add(dimension_id)
            if not dimension.get("covered", False) and dimension.get("required", False):
                missing.add(dimension_id)

            rubric_node_id = _rubric_node_id(dimension_id)
            graph.add_node(rubric_node_id, "rubric_dimension", dimension.get("description") or dimension_id, {
                "dimension_id": dimension_id,
                "description": dimension.get("description"),
                "required": bool(dimension.get("required")),
                "prefers_web": bool(dimension.get("prefers_web")),
                "covered": bool(dimension.get("covered")),
                "score": dimension.get("score"),
                "keywords": dimension.get("keywords") or [],
            })
            for evidence_id in dimension.get("evidence_ids") or []:
                if evidence_id not in evidence_by_id:
                    continue
                graph.add_edge(_evidence_node_id(evidence_id), rubric_node_id, "covers", _safe_float(dimension.get("score"), 0.0), {
                    "dimension_id": dimension_id,
                })

        for dimension_id in gap.get("missing_required") or []:
            if dimension_id:
                missing.add(_clean(dimension_id))
        for dimension_id in gap.get("preferred_web_missing") or []:
            if not dimension_id:
                continue
            rubric_node_id = _rubric_node_id(dimension_id)
            graph.add_node(rubric_node_id, "rubric_dimension", _clean(dimension_id), {
                "dimension_id": _clean(dimension_id),
                "prefers_web": True,
                "covered": False,
                "web_missing": True,
            })

    return {
        "dimension_count": len(seen_dimensions),
        "missing": sorted(missing),
    }


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


def _rubric_dimensions_by_evidence(root_node_json: Dict[str, Any]) -> Dict[str, List[str]]:
    mapping = defaultdict(list)
    for gap in _iter_rubric_gaps(root_node_json):
        for dimension in gap.get("dimensions") or []:
            dimension_id = _clean(dimension.get("dimension_id"))
            if not dimension_id:
                continue
            for evidence_id in dimension.get("evidence_ids") or []:
                evidence_id = _clean(evidence_id)
                if evidence_id and dimension_id not in mapping[evidence_id]:
                    mapping[evidence_id].append(dimension_id)
    return dict(mapping)


def _extract_cited_claims(text: str) -> List[str]:
    claims = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or not _has_citation(stripped):
            continue
        if _looks_like_table_separator(stripped):
            continue
        for fragment in _split_claim_fragments(stripped):
            if _has_citation(fragment):
                claims.append(fragment)
    return claims


def _split_claim_fragments(text: str) -> List[str]:
    if "|" in text and text.count("|") >= 2:
        return [cell.strip() for cell in text.strip("|").split("|") if cell.strip()]
    return [text]


def _has_citation(text: str) -> bool:
    return bool(REFERENCE_CITATION_RE.search(text) or DISPLAY_CITATION_RE.search(text))


def _citation_evidence_ids(
    text: str,
    evidence_by_global_index: Dict[int, str],
    evidence_by_display_label: Dict[str, str],
) -> List[str]:
    ids = []
    seen = set()

    for match in REFERENCE_CITATION_RE.finditer(text or ""):
        global_index = _safe_int(match.group(1))
        evidence_id = evidence_by_global_index.get(global_index)
        if evidence_id and evidence_id not in seen:
            seen.add(evidence_id)
            ids.append(evidence_id)

    for match in DISPLAY_CITATION_RE.finditer(text or ""):
        label = "{}:{}".format(match.group(1).upper(), match.group(2))
        evidence_id = evidence_by_display_label.get(label)
        if evidence_id and evidence_id not in seen:
            seen.add(evidence_id)
            ids.append(evidence_id)
    return ids


def _build_display_label_map(items: List[Dict[str, Any]]) -> Dict[str, str]:
    mapping = {}
    counters = defaultdict(int)
    sorted_items = sorted(
        [item for item in items if item.get("evidence_id")],
        key=lambda item: (_safe_int(item.get("global_index")) is None, _safe_int(item.get("global_index")) or 0),
    )
    for item in sorted_items:
        source_type = _clean(item.get("source_type") or "unknown").lower()
        if source_type not in ("kb", "web"):
            continue
        counters[source_type] += 1
        mapping["{}:{}".format(source_type.upper(), counters[source_type])] = item.get("evidence_id")
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


def _strip_citations(text: str) -> str:
    text = REFERENCE_CITATION_RE.sub("", text or "")
    text = DISPLAY_CITATION_RE.sub("", text)
    text = re.sub(r"\]\([^)]+\)", "", text)
    text = re.sub(r"^[#>\-\*\d\.\s]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return _trim(text.strip(" |"), 260)


def _looks_like_table_separator(text: str) -> bool:
    compact = text.replace("|", "").replace(":", "").replace("-", "").strip()
    return compact == ""


def _evidence_node_id(evidence_id: str) -> str:
    return "evidence:{}".format(_clean(evidence_id))


def _source_node_id(value: str) -> str:
    return "source:{}".format(_hash(value or "unknown"))


def _cluster_node_id(source_type: str, source_value: str) -> str:
    return "cluster:{}".format(_hash("{}\n{}".format(source_type or "unknown", source_value or "unknown")))


def _task_node_id(value: Any) -> str:
    return "task:{}".format(_clean(value) or "unknown")


def _rubric_node_id(value: str) -> str:
    return "rubric:{}".format(_hash(_clean(value), length=12))


def _section_node_id(index: int, title: Optional[str]) -> str:
    return "section:{}:{}".format(index, _hash(title or str(index), length=10))


def _section_map_node_id(section_id: str) -> str:
    return "section_evidence_map:{}".format(_hash(section_id, length=12))


def _claim_node_id(section_id: str, text: str) -> str:
    return "claim:{}".format(_hash("{}\n{}".format(section_id, text), length=16))


def _hash(value: str, length: int = 16) -> str:
    return hashlib.sha1(_clean(value).encode("utf-8", errors="ignore")).hexdigest()[:length]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _trim(value: Any, limit: int = 200) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any, default: float = 1.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        if isinstance(value, dict):
            return {str(k): _jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_jsonable(v) for v in value]
        return _clean(value)
