from followup_test_utils import load_followup_module


editor_module = load_followup_module("editor")
run_followup_edit = editor_module.run_followup_edit


def test_followup_edit_rewrites_target_section_only_with_evidence_payload():
    report = (
        "# Report\n\n"
        "## Market Analysis\n"
        "Old market text. [reference:1]\n\n"
        "## Roadmap\n"
        "Roadmap text.\n\n"
        "## References\n"
        "- source\n"
    )
    artifacts = {
        "evidence_graph": {
            "nodes": [
                {
                    "type": "evidence",
                    "data": {
                        "evidence_id": "e1",
                        "source_type": "kb",
                        "source_title": "market.md",
                        "citation_label": "[reference:1]",
                        "preview": "Market evidence.",
                    },
                }
            ],
            "summary": {
                "section_evidence_map": [
                    {
                        "section_title": "Market Analysis",
                        "evidence_ids": ["e1"],
                    }
                ]
            },
        }
    }

    def fake_edit(payload):
        assert payload["section_title"] == "Market Analysis"
        assert payload["relevant_evidence"][0]["evidence_id"] == "e1"
        return "## Market Analysis\nUpdated market text with evidence. [reference:1]"

    updated, record = run_followup_edit(
        report=report,
        instruction="Please polish Market Analysis.",
        artifacts=artifacts,
        edit_client=fake_edit,
    )

    assert record["edited_section_count"] == 1
    assert "Updated market text" in updated
    assert "Roadmap text." in updated
    assert "## References" in updated


def test_followup_edit_requires_model_without_fake_client():
    updated, record = run_followup_edit(
        report="# Report\nText.",
        instruction="Polish it.",
        artifacts={},
        model=None,
    )

    assert updated.startswith("# Report")
    assert record["edited_section_count"] == 0
    assert record["error"]


def test_followup_edit_runs_search_repair_for_evidence_sensitive_expansion():
    report = (
        "# Report\n\n"
        "## 竞品分析\n"
        "旧竞品内容。 [reference:1]\n\n"
        "## References\n"
        "- [reference:1] KB: old.md\n"
    )
    captured = {}

    def fake_search_repair_runner(**kwargs):
        assert kwargs["kb_name"] == "large_kb"
        assert kwargs["execute_kb"] is True
        assert kwargs["writer_feedback"]["actions"][0]["target_rubric_dimension"] == "competitors"
        return {
            "version": "1.0",
            "enabled": True,
            "executed": True,
            "kb_name": "large_kb",
            "queries": ["AgC 竞品对比 厂商分析"],
            "new_evidence_ids": ["sr1"],
            "kb_results": [
                {
                    "evidence_id": "sr1",
                    "citation_label": "[reference:2]",
                    "source_type": "kb",
                    "verify_label": "direct_support",
                    "title": "competitors.md",
                    "source": "docs/competitors.md",
                    "summary": "竞品能力矩阵证据。",
                    "search_query": "AgC 竞品对比 厂商分析",
                }
            ],
            "summary": {
                "query_count": 1,
                "kb_result_count": 1,
                "new_evidence_count": 1,
                "executed": True,
            },
        }

    def fake_edit(payload):
        captured["payload"] = payload
        assert payload["relevant_evidence"][0]["evidence_id"] == "sr1"
        return "## 竞品分析\n新增竞品矩阵结论。 [reference:2]"

    updated, record = run_followup_edit(
        report=report,
        instruction="补充竞品对标分析",
        artifacts={},
        edit_client=fake_edit,
        enable_search_repair=True,
        kb_name="large_kb",
        search_repair_runner=fake_search_repair_runner,
    )

    assert captured["payload"]["relevant_evidence"][0]["citation_label"] == "[reference:2]"
    assert record["search_repair"]["summary"]["new_evidence_count"] == 1
    assert "新增竞品矩阵结论" in updated
    assert "### Follow-up Evidence" in updated
    assert "- [reference:2] KB: competitors.md" in updated
