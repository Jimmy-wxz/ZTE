from evidence_test_utils import load_evidence_module


repair_module = load_evidence_module("repair_loop")
run_writer_repair_loop = repair_module.run_writer_repair_loop


def test_repair_loop_rewrites_target_section_only():
    article = (
        "# Report\n\n"
        "## Roadmap\n"
        "The total budget is 4.3 million RMB and ROI reaches 200%.\n\n"
        "## References\n"
        "- [KB:1] source\n"
    )
    writer_feedback = {
        "actions": [
            {
                "action_type": "rewrite_or_cite_claim",
                "severity": "high",
                "target_section": "Roadmap",
                "claim_text": "The total budget is 4.3 million RMB and ROI reaches 200%.",
            }
        ],
        "section_feedback": [
            {
                "section_title": "Roadmap",
                "evidence_ids": ["e1"],
            }
        ],
    }
    ledger_items = [
        {
            "evidence_id": "e1",
            "source_type": "kb",
            "source_title": "Planning source",
            "citation_label": "[reference:1]",
            "chunk_text": "The source describes implementation stages but does not provide ROI.",
        }
    ]

    def fake_repair(payload):
        assert payload["section_title"] == "Roadmap"
        assert payload["evidence"][0]["evidence_id"] == "e1"
        return "## Roadmap\nThe implementation budget requires validation; retrieved evidence does not support a precise ROI estimate. [reference:1]"

    repaired, report = run_writer_repair_loop(
        article=article,
        writer_feedback=writer_feedback,
        ledger_items=ledger_items,
        repair_client=fake_repair,
    )

    assert report["repaired_section_count"] == 1
    assert "4.3 million" not in repaired
    assert "## References" in repaired
    assert "requires validation" in repaired


def test_repair_loop_skips_when_no_actions():
    article = "# Report\n\n## Roadmap\nOK.\n"

    repaired, report = run_writer_repair_loop(
        article=article,
        writer_feedback={"actions": []},
        repair_client=lambda payload: payload["section_markdown"],
    )

    assert repaired == article
    assert report["enabled"] is False


def test_repair_loop_includes_search_repair_evidence():
    article = (
        "# Report\n\n"
        "## Market\n"
        "Competitor capability claims need better support.\n"
    )
    writer_feedback = {
        "actions": [
            {
                "action_type": "minimal_section_rewrite",
                "severity": "medium",
                "target_section": "Market",
                "search_repair_evidence_ids": ["repair1"],
            }
        ],
        "section_feedback": [{"section_title": "Market"}],
        "search_repair_evidence_ids": ["repair1"],
    }
    ledger_items = [
        {
            "evidence_id": "repair1",
            "source_type": "kb",
            "source_title": "Competitor source",
            "citation_label": "[reference:7]",
            "chunk_text": "The evidence compares vendor capabilities and deployment constraints.",
        }
    ]

    def fake_repair(payload):
        assert payload["evidence"][0]["evidence_id"] == "repair1"
        assert payload["evidence"][0]["citation_label"] == "[reference:7]"
        return "## Market\nVendor capabilities should be compared against deployment constraints. [reference:7]"

    repaired, report = run_writer_repair_loop(
        article=article,
        writer_feedback=writer_feedback,
        ledger_items=ledger_items,
        repair_client=fake_repair,
    )

    assert report["repaired_section_count"] == 1
    assert "[reference:7]" in repaired
