import tempfile
from pathlib import Path

from policy_test_utils import load_policy_module


history_module = load_policy_module("history_store")
HistoryStore = history_module.HistoryStore
build_history_record = history_module.build_history_record


def test_history_store_appends_recent_records_and_summarizes_matches():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "policy_history.jsonl"
        store = HistoryStore(str(path))
        record = build_history_record(
            task_id="task-1",
            features={
                "prompt_hash": "abc",
                "language": "en",
                "task_family": "market_competitor",
                "complexity_score": 0.5,
                "engine_backend": "google",
                "kb_name": "large_kb",
            },
            decision={
                "recommendation": {
                    "search_mode": "wide",
                    "model_profile": {"writer": "deepseek-chat"},
                    "enable_web": True,
                    "enable_claim_verifier": False,
                },
                "applied_to_runtime": False,
            },
            outcome={
                "status": "completed",
                "timing": {"total_duration_seconds": 120},
                "scores": {"quality_score": 78, "reward": 74},
                "quality": {
                    "unsupported_claim_count": 1,
                    "citation_count": 12,
                    "kb_evidence_count": 7,
                    "web_evidence_count": 3,
                },
            },
        )
        store.append(record)

        recent = store.load_recent(limit=5)
        summary = store.summarize({
            "language": "en",
            "task_family": "market_competitor",
        })

        assert len(recent) == 1
        assert summary["matching_count"] == 1
        assert summary["mode_stats"]["wide"]["avg_reward"] == 74


def test_history_store_ignores_missing_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        store = HistoryStore(str(Path(temp_dir) / "missing.jsonl"))

        assert store.load_recent(limit=5) == []
        assert store.summarize({"task_family": "general_report"})["recent_count"] == 0
