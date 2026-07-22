from policy_test_utils import load_policy_module


outcome_module = load_policy_module("outcome_analyzer")
build_policy_outcome = outcome_module.build_policy_outcome


def test_policy_outcome_extracts_quality_and_reward_metrics():
    outcome = build_policy_outcome(
        task_id="task-1",
        prompt="Write report.",
        decision={
            "features": {"prompt_hash": "abc"},
            "recommendation": {
                "search_mode": "wide",
                "model_profile": {"writer": "deepseek-chat"},
            },
        },
        result="# Report\n\n## Market\nEvidence backed sentence. [KB:1]\n\n| A | B |\n|---|---|\n| x | y |\n",
        timing={
            "total_duration_seconds": 90,
            "generation_seconds": 70,
        },
        evidence_graph={
            "summary": {
                "evidence_total": 3,
                "cited_evidence": 1,
                "source_type_counts": {"kb": 2, "web": 1},
                "rubric_missing": [],
            }
        },
        claim_verification={
            "summary": {
                "unsupported_count": 0,
                "needs_review_count": 1,
            }
        },
        quality_audit={
            "low_citation_section_count": 0,
            "unsupported_quantitative_count": 0,
        },
        search_repair={
            "summary": {"new_evidence_count": 1}
        },
        repair_report={
            "attempted_section_count": 1,
            "repaired_section_count": 1,
        },
    )

    assert outcome["status"] == "completed"
    assert outcome["quality"]["citation_count"] == 1
    assert outcome["quality"]["kb_evidence_count"] == 2
    assert outcome["quality"]["web_evidence_count"] == 1
    assert outcome["scores"]["quality_score"] > 55
    assert outcome["scores"]["reward"] < outcome["scores"]["quality_score"]


def test_policy_outcome_penalizes_failed_runs():
    outcome = build_policy_outcome(
        task_id="task-error",
        prompt="Write report.",
        decision={},
        status="error",
        error="boom",
    )

    assert outcome["scores"]["quality_score"] == 0.0
    assert outcome["scores"]["reward"] == -50.0
