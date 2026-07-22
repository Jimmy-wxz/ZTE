# coding:utf8

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


ARTIFACT_FILES = {
    "evidence_graph": "evidence_graph.json",
    "claim_verification": "claim_verification.json",
    "writer_feedback": "writer_feedback.json",
    "search_repair": "search_repair.json",
    "repair_loop": "repair_loop.json",
    "report_quality_audit": "report_quality_audit.json",
    "policy_decision": "policy_decision.json",
    "policy_outcome": "policy_outcome.json",
    "followup_search_repair": "followup_search_repair.json",
}


def find_records_dir(results_dir: str, task_id: str) -> str:
    candidates = [
        os.path.join(results_dir, "records", task_id),
        os.path.join(results_dir, task_id, "records"),
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return candidates[0]


def load_latest_report(results_dir: str, task_id: str) -> Tuple[str, str]:
    records_dir = find_records_dir(results_dir, task_id)
    latest_meta = os.path.join(records_dir, "report_versions", "latest.json")
    if os.path.exists(latest_meta):
        try:
            with open(latest_meta, "r", encoding="utf-8") as f:
                meta = json.load(f)
            version_path = meta.get("report_path")
            if version_path and os.path.exists(version_path):
                return _read_text(version_path), records_dir
        except Exception:
            pass
    report_path = os.path.join(records_dir, "report.md")
    if os.path.exists(report_path):
        return _read_text(report_path), records_dir
    fallback = os.path.join(results_dir, task_id, "result.jsonl")
    if os.path.exists(fallback):
        try:
            with open(fallback, "r", encoding="utf-8") as f:
                first = f.readline()
            data = json.loads(first)
            return data.get("result", ""), records_dir
        except Exception:
            pass
    raise FileNotFoundError("No report found for task {}".format(task_id))


def load_followup_artifacts(records_dir: str) -> Dict[str, Any]:
    artifacts = {}
    for key, filename in ARTIFACT_FILES.items():
        path = os.path.join(records_dir, filename)
        if not os.path.exists(path):
            artifacts[key] = {}
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                artifacts[key] = json.load(f)
        except Exception:
            artifacts[key] = {}
    return artifacts


def save_report_version(
    records_dir: str,
    report: str,
    edit_record: Dict[str, Any],
    task_dir: Optional[str] = None,
) -> Dict[str, Any]:
    versions_dir = os.path.join(records_dir, "report_versions")
    os.makedirs(versions_dir, exist_ok=True)
    version_id = _version_id()
    report_path = os.path.join(versions_dir, "{}.md".format(version_id))
    meta_path = os.path.join(versions_dir, "{}.json".format(version_id))
    current_report_path = os.path.join(records_dir, "report.md")

    _write_text(report_path, report)
    _write_text(current_report_path, report)
    metadata = dict(edit_record or {})
    metadata.update({
        "version_id": version_id,
        "report_path": report_path,
        "metadata_path": meta_path,
        "current_report_path": current_report_path,
    })
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    with open(os.path.join(versions_dir, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    with open(os.path.join(records_dir, "followup_edit.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    if task_dir:
        _update_result_jsonl(task_dir, report)
    return metadata


def save_followup_search_repair(
    records_dir: str,
    search_repair: Optional[Dict[str, Any]],
) -> str:
    if not search_repair:
        return ""
    path = os.path.join(records_dir, ARTIFACT_FILES["followup_search_repair"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(search_repair, f, indent=2, ensure_ascii=False)
    return path


def append_followup_history(
    results_dir: str,
    task_id: str,
    metadata: Dict[str, Any],
) -> None:
    history_path = os.environ.get(
        "WRITEHERE_POLICY_HISTORY_PATH",
        os.path.join(results_dir, "policy_history.jsonl"),
    )
    try:
        os.makedirs(os.path.dirname(os.path.abspath(history_path)), exist_ok=True)
        intent = metadata.get("intent") or {}
        record = {
            "version": "1.0",
            "record_type": "followup_edit",
            "task_id": task_id,
            "version_id": metadata.get("version_id"),
            "created_at": metadata.get("created_at"),
            "instruction": metadata.get("instruction"),
            "intent": {
                "intent_type": intent.get("intent_type"),
                "scope": intent.get("scope"),
                "requires_search_repair": intent.get("requires_search_repair"),
                "risk_level": intent.get("risk_level"),
            },
            "target_sections": metadata.get("target_sections") or [],
            "edited_section_count": metadata.get("edited_section_count", 0),
            "status": metadata.get("status", ""),
            "search_repair": _history_search_repair(metadata.get("search_repair") or {}),
        }
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        return


def list_report_versions(records_dir: str) -> List[Dict[str, Any]]:
    versions_dir = os.path.join(records_dir, "report_versions")
    if not os.path.isdir(versions_dir):
        return []
    versions = []
    for name in os.listdir(versions_dir):
        if not name.endswith(".json") or name == "latest.json":
            continue
        path = os.path.join(versions_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                versions.append(json.load(f))
        except Exception:
            continue
    return sorted(versions, key=lambda item: item.get("created_at", ""))


def _update_result_jsonl(task_dir: str, report: str) -> None:
    path = os.path.join(task_dir, "result.jsonl")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            line = f.readline()
        data = json.loads(line) if line.strip() else {}
        data["result"] = report
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception:
        return


def _version_id() -> str:
    return "v{}".format(datetime.now().strftime("%Y%m%d_%H%M%S_%f"))


def _history_search_repair(search_repair: Dict[str, Any]) -> Dict[str, Any]:
    summary = search_repair.get("summary") or {}
    return {
        "enabled": bool(search_repair.get("enabled")),
        "executed": bool(search_repair.get("executed")),
        "kb_name": search_repair.get("kb_name", ""),
        "query_count": summary.get("query_count", 0),
        "kb_result_count": summary.get("kb_result_count", 0),
        "new_evidence_count": summary.get("new_evidence_count", 0),
        "error": search_repair.get("error", ""),
    }


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(text or ""))
