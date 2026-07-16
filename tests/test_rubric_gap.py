from evidence_test_utils import load_evidence_modules


_, rubric_module = load_evidence_modules()
evaluate_rubric_gap = rubric_module.evaluate_rubric_gap


def test_rubric_gap_requests_supplement_for_missing_market_and_competitors():
    pages = [
        {
            "title": "Local KB: AIOps architecture",
            "summary": "AIOps platform architecture includes data collection, anomaly detection, and automated remediation.",
            "evidence": {
                "evidence_id": "ev1",
                "source_type": "kb",
                "verify_label": "direct_support",
                "verify_score": 0.88,
                "chunk_text": "AIOps platform architecture includes anomaly detection.",
            },
        }
    ]

    result = evaluate_rubric_gap(
        "Write a technology market report with competitor and market opportunity analysis for telecom AIOps.",
        pages,
        min_supported_pages=1,
    )

    assert result["should_supplement_web"] is True
    assert "competitors" in result["missing_required"]
    assert "market_context" in result["missing_required"]


def test_rubric_gap_passes_when_required_dimensions_are_supported():
    pages = [
        {
            "title": "AIOps technology definition and application scenarios",
            "summary": "AIOps technology supports telecom network application scenarios and architecture automation.",
            "evidence": {
                "evidence_id": "ev1",
                "source_type": "kb",
                "verify_label": "direct_support",
                "verify_score": 0.91,
                "chunk_text": "AIOps technology supports telecom network application scenarios.",
            },
        },
        {
            "title": "AIOps vendor market comparison",
            "summary": "The AIOps market includes vendor comparison, competitor positioning, and growth trends.",
            "evidence": {
                "evidence_id": "ev2",
                "source_type": "web",
                "verify_label": "direct_support",
                "verify_score": 0.87,
                "chunk_text": "The market includes vendor comparison and growth trends.",
            },
        },
    ]

    result = evaluate_rubric_gap(
        "Write a technology market report with competitor and market opportunity analysis for telecom AIOps.",
        pages,
        min_supported_pages=1,
    )

    assert result["missing_required"] == []
    assert result["should_supplement_web"] is False
