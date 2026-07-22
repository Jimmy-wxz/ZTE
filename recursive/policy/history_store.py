# coding:utf8

import json
import os
import threading
from typing import Any, Dict, Iterable, List, Optional


class HistoryStore:
    """Append-only JSONL history for adaptive report policy experiments."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get(
            "WRITEHERE_POLICY_HISTORY_PATH",
            os.path.join("runtime_logs", "policy_history.jsonl"),
        )
        self._lock = threading.RLock()

    def append(self, record: Dict[str, Any]) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load_recent(self, limit: int = 200) -> List[Dict[str, Any]]:
        if not self.path or not os.path.exists(self.path):
            return []
        limit = max(0, int(limit or 0))
        if limit == 0:
            return []
        with self._lock:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-limit:]
        records = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except Exception:
                continue
        return records

    def summarize(
        self,
        features: Dict[str, Any] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        records = self.load_recent(limit=limit)
        features = features or {}
        family = features.get("task_family")
        language = features.get("language")
        matching = [
            record for record in records
            if _nested_get(record, ("features", "task_family")) == family
            and (not language or _nested_get(record, ("features", "language")) == language)
        ]
        return {
            "history_path": self.path,
            "recent_count": len(records),
            "matching_count": len(matching),
            "matching_task_family": family or "",
            "matching_language": language or "",
            "mode_stats": _mode_stats(matching),
        }


def build_history_record(
    task_id: str,
    features: Dict[str, Any],
    decision: Dict[str, Any],
    outcome: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "version": "1.0",
        "record_type": "policy_run",
        "task_id": task_id,
        "features": {
            "prompt_hash": features.get("prompt_hash"),
            "language": features.get("language"),
            "task_family": features.get("task_family"),
            "complexity_score": features.get("complexity_score"),
            "engine_backend": features.get("engine_backend"),
            "kb_name": features.get("kb_name"),
        },
        "decision": {
            "policy_strategy": decision.get("policy_strategy", ""),
            "recommended_search_mode": _nested_get(
                decision, ("recommendation", "search_mode")),
            "recommended_model_profile": _nested_get(
                decision, ("recommendation", "model_profile")),
            "bandit_selected_mode": _nested_get(
                decision, ("bandit_selection", "selected_mode")),
            "bandit_algorithm": _nested_get(
                decision, ("bandit_selection", "algorithm")),
            "enable_web": _nested_get(decision, ("recommendation", "enable_web")),
            "enable_claim_verifier": _nested_get(
                decision, ("recommendation", "enable_claim_verifier")),
            "applied_to_runtime": decision.get("applied_to_runtime", False),
        },
        "outcome": {
            "status": outcome.get("status", "completed"),
            "total_duration_seconds": _nested_get(
                outcome, ("timing", "total_duration_seconds")),
            "quality_score": _nested_get(outcome, ("scores", "quality_score")),
            "reward": _nested_get(outcome, ("scores", "reward")),
            "unsupported_claim_count": _nested_get(
                outcome, ("quality", "unsupported_claim_count")),
            "citation_count": _nested_get(outcome, ("quality", "citation_count")),
            "kb_evidence_count": _nested_get(
                outcome, ("quality", "kb_evidence_count")),
            "web_evidence_count": _nested_get(
                outcome, ("quality", "web_evidence_count")),
        },
    }


def _mode_stats(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    stats: Dict[str, Dict[str, float]] = {}
    for record in records:
        mode = _nested_get(record, ("decision", "recommended_search_mode")) or "unknown"
        reward = _safe_float(_nested_get(record, ("outcome", "reward")))
        quality = _safe_float(_nested_get(record, ("outcome", "quality_score")))
        duration = _safe_float(_nested_get(record, ("outcome", "total_duration_seconds")))
        bucket = stats.setdefault(mode, {
            "count": 0,
            "avg_reward": 0.0,
            "avg_quality_score": 0.0,
            "avg_duration_seconds": 0.0,
        })
        bucket["count"] += 1
        n = bucket["count"]
        bucket["avg_reward"] += (reward - bucket["avg_reward"]) / n
        bucket["avg_quality_score"] += (quality - bucket["avg_quality_score"]) / n
        bucket["avg_duration_seconds"] += (duration - bucket["avg_duration_seconds"]) / n
    for bucket in stats.values():
        for key in ("avg_reward", "avg_quality_score", "avg_duration_seconds"):
            bucket[key] = round(bucket[key], 4)
    return stats


def _nested_get(obj: Dict[str, Any], path, default=None):
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0
