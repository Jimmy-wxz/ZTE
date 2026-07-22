import tempfile
from pathlib import Path

from followup_test_utils import load_followup_module


store_module = load_followup_module("session_store")
append_followup_history = store_module.append_followup_history
find_records_dir = store_module.find_records_dir
list_report_versions = store_module.list_report_versions
load_latest_report = store_module.load_latest_report
load_followup_artifacts = store_module.load_followup_artifacts
save_followup_search_repair = store_module.save_followup_search_repair
save_report_version = store_module.save_report_version


def test_session_store_saves_version_and_latest_report():
    with tempfile.TemporaryDirectory() as temp_dir:
        results_dir = Path(temp_dir)
        records_dir = results_dir / "records" / "task-1"
        records_dir.mkdir(parents=True)
        (records_dir / "report.md").write_text("# Old\n", encoding="utf-8")

        metadata = save_report_version(
            str(records_dir),
            "# New\n",
            {"instruction": "edit", "edited_section_count": 1},
        )
        report, loaded_records_dir = load_latest_report(str(results_dir), "task-1")
        versions = list_report_versions(str(records_dir))

        assert metadata["version_id"]
        assert report == "# New\n"
        assert loaded_records_dir == str(records_dir)
        assert len(versions) == 1
        assert versions[0]["instruction"] == "edit"


def test_find_records_dir_prefers_global_records_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        results_dir = Path(temp_dir)
        global_records = results_dir / "records" / "task-1"
        task_records = results_dir / "task-1" / "records"
        global_records.mkdir(parents=True)
        task_records.mkdir(parents=True)

        assert find_records_dir(str(results_dir), "task-1") == str(global_records)


def test_append_followup_history_writes_feedback_signal():
    with tempfile.TemporaryDirectory() as temp_dir:
        append_followup_history(
            temp_dir,
            "task-1",
            {
                "version_id": "v1",
                "created_at": "2026-07-22T10:00:00",
                "instruction": "补充竞品分析",
                "intent": {
                    "intent_type": "expand",
                    "requires_search_repair": True,
                    "scope": "section",
                    "risk_level": "medium",
                },
                "target_sections": [{"title": "竞品分析"}],
                "edited_section_count": 1,
                "status": "edited",
            },
        )

        history = Path(temp_dir) / "policy_history.jsonl"
        assert history.exists()
        assert '"record_type": "followup_edit"' in history.read_text(encoding="utf-8")


def test_session_store_persists_followup_search_repair_artifact():
    with tempfile.TemporaryDirectory() as temp_dir:
        records_dir = Path(temp_dir) / "records" / "task-1"
        records_dir.mkdir(parents=True)
        path = save_followup_search_repair(
            str(records_dir),
            {
                "executed": True,
                "summary": {"new_evidence_count": 1},
                "kb_results": [{"evidence_id": "sr1"}],
            },
        )

        artifacts = load_followup_artifacts(str(records_dir))

        assert Path(path).exists()
        assert artifacts["followup_search_repair"]["summary"]["new_evidence_count"] == 1
