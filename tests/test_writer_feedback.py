from evidence_test_utils import load_evidence_module


feedback_module = load_evidence_module("writer_feedback")
build_writer_feedback = feedback_module.build_writer_feedback


def test_writer_feedback_creates_actions_for_unsupported_claims_and_rubric_gaps():
    claim_verification = {
        "unsupported_claims": [
            {
                "claim_id": "c1",
                "section_title": "Roadmap",
                "text": "ROI reaches 200%.",
                "risk_level": "high",
                "status": "unsupported",
            }
        ],
        "claims": [
            {
                "claim_id": "c1",
                "section_title": "Roadmap",
                "text": "ROI reaches 200%.",
                "risk_level": "high",
                "status": "unsupported",
            }
        ],
    }
    quality_audit = {
        "section_citation_metrics": [
            {
                "title": "Roadmap",
                "start_line": 3,
                "end_line": 8,
                "citation_count": 0,
                "char_count": 300,
            }
        ],
        "low_citation_sections": [
            {
                "title": "Roadmap",
                "citation_count": 0,
                "char_count": 300,
            }
        ],
    }
    root_node_json = {
        "result": {
            "rubric_gap": {
                "dimensions": [],
                "missing_required": ["market_context"],
                "preferred_web_missing": ["competitors"],
            }
        }
    }

    feedback = build_writer_feedback(
        claim_verification=claim_verification,
        quality_audit=quality_audit,
        root_node_json=root_node_json,
    )

    action_types = {action["action_type"] for action in feedback["actions"]}
    assert "rewrite_or_cite_claim" in action_types
    assert "increase_section_citations" in action_types
    assert "supplement_missing_rubric_dimension" in action_types
    assert feedback["summary"]["repair_needed"] is True


def test_writer_feedback_uses_section_evidence_map():
    evidence_graph = {
        "summary": {
            "section_evidence_map": [
                {
                    "section_title": "Architecture",
                    "evidence_ids": ["e1", "e2"],
                    "kb_evidence_count": 1,
                    "web_evidence_count": 1,
                    "rubric_dimensions": ["technology_definition"],
                }
            ]
        }
    }

    feedback = build_writer_feedback(evidence_graph=evidence_graph)

    section = feedback["section_feedback"][0]
    assert section["section_title"] == "Architecture"
    assert section["evidence_ids"] == ["e1", "e2"]
    assert section["kb_evidence_count"] == 1
    assert section["web_evidence_count"] == 1
