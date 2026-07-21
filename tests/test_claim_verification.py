from evidence_test_utils import load_evidence_module


claim_module = load_evidence_module("claim_verification")
verify_report_claims = claim_module.verify_report_claims
select_claims_for_llm_verification = claim_module.select_claims_for_llm_verification


def test_claim_verification_supports_cited_claims():
    ledger_items = [
        {
            "evidence_id": "e1",
            "source_type": "kb",
            "source_uri": "local-kb:///iast.md",
            "source_title": "iast.md",
            "chunk_text": "IAST observes runtime behavior during testing and detects vulnerabilities.",
            "verify_label": "direct_support",
            "verify_score": 0.91,
            "global_index": 1,
        }
    ]
    article = "# Overview\nIAST observes runtime behavior during testing. [reference:1]\n"

    result = verify_report_claims(article=article, ledger_items=ledger_items)

    assert result["summary"]["claim_count"] == 1
    assert result["claims"][0]["status"] == "supported"
    assert result["claims"][0]["supporting_evidence_ids"] == ["e1"]


def test_claim_verification_flags_unsupported_high_risk_numbers():
    article = "# Roadmap\nThe total budget is 4.3 million RMB and ROI reaches 200%.\n"

    result = verify_report_claims(article=article, ledger_items=[])

    assert result["summary"]["unsupported_count"] == 1
    assert result["unsupported_claims"][0]["risk_level"] == "high"


def test_claim_verification_marks_weak_cited_claim_as_partial():
    ledger_items = [
        {
            "evidence_id": "e2",
            "source_type": "web",
            "source_uri": "https://example.com",
            "source_title": "Market overview",
            "chunk_text": "The market includes several vendors.",
            "verify_label": "background",
            "verify_score": 0.2,
            "global_index": 2,
        }
    ]
    article = "# Market\nThe platform has complete zero-day exploit protection. [reference:2]\n"

    result = verify_report_claims(article=article, ledger_items=ledger_items)

    assert result["claims"][0]["status"] in ("partially_supported", "needs_review")


def test_selective_llm_verifier_updates_high_risk_claim_status():
    article = "# Roadmap\nThe total budget is 4.3 million RMB and ROI reaches 200%.\n"

    def fake_verifier(payload):
        assert len(payload) == 1
        return {
            "results": [
                {
                    "claim_id": payload[0]["claim_id"],
                    "label": "unsupported",
                    "evidence_ids": [],
                    "reason": "No evidence was provided.",
                    "rewrite_suggestion": "Mark the number as an estimate or remove it.",
                }
            ]
        }

    result = verify_report_claims(
        article=article,
        ledger_items=[],
        llm_verifier=True,
        max_llm_claims=3,
        verifier_client=fake_verifier,
    )

    assert result["llm_verifier"]["applied_count"] == 1
    assert result["summary"]["llm_verified_claim_count"] == 1
    assert result["claims"][0]["verification_source"] == "llm"
    assert result["claims"][0]["llm_rewrite_suggestion"]


def test_select_claims_for_llm_verification_prioritizes_high_risk():
    claims = [
        {"claim_id": "low", "status": "partially_supported", "risk_level": "medium", "line_number": 1},
        {"claim_id": "high", "status": "unsupported", "risk_level": "high", "line_number": 2},
    ]

    selected = select_claims_for_llm_verification(claims, max_claims=1)

    assert selected[0]["claim_id"] == "high"
