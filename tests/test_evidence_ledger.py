from evidence_test_utils import load_evidence_modules


ledger_module, _ = load_evidence_modules()
EvidenceLedger = ledger_module.EvidenceLedger
annotate_page_evidence = ledger_module.annotate_page_evidence


def test_annotate_page_evidence_builds_kb_unit():
    page = {
        "global_index": 3,
        "title": "Local KB: iast.json",
        "url": "local-kb:///doc/iast.json",
        "summary": "IAST is an interactive application security testing technique.",
        "rerank_score": 0.9,
    }

    annotate_page_evidence(
        page=page,
        node_id="1",
        node_goal="Explain IAST security testing",
        source_type="kb",
    )

    evidence = page["evidence"]
    assert evidence["source_type"] == "kb"
    assert evidence["source_uri"] == "local-kb:///doc/iast.json"
    assert evidence["verify_label"] in ("direct_support", "partial_support")
    assert evidence["citation_label"] == "[reference:3]"


def test_evidence_ledger_register_page_updates_global_index():
    page = {
        "title": "Market report",
        "url": "https://example.com/report",
        "summary": "The telecom AIOps market report compares vendor platforms.",
    }
    annotate_page_evidence(
        page=page,
        node_id="2",
        node_goal="Compare telecom AIOps market vendors",
        source_type="web",
    )
    page["global_index"] = 7

    ledger = EvidenceLedger()
    item = ledger.register_page(page)

    assert item["source_type"] == "web"
    assert item["global_index"] == 7
    assert item["citation_label"] == "[reference:7]"
    assert ledger.to_list()[0]["evidence_id"] == page["evidence_id"]
