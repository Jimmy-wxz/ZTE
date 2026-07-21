from evidence_test_utils import load_evidence_graph_module, load_evidence_module


graph_module = load_evidence_graph_module()
claim_module = load_evidence_module("claim_verification")
writer_feedback_module = load_evidence_module("writer_feedback")
search_repair_module = load_evidence_module("search_repair")
repair_loop_module = load_evidence_module("repair_loop")

build_evidence_graph = graph_module.build_evidence_graph
verify_report_claims = claim_module.verify_report_claims
build_writer_feedback = writer_feedback_module.build_writer_feedback
run_search_repair = search_repair_module.run_search_repair
augment_writer_feedback_with_search_repair = (
    search_repair_module.augment_writer_feedback_with_search_repair
)
run_writer_repair_loop = repair_loop_module.run_writer_repair_loop


class FakeMemory:
    def __init__(self):
        self.global_start_index = 9
        self.added = []

    def add_search_result(self, page):
        page["global_index"] = self.global_start_index
        evidence = page.get("evidence") or {}
        evidence["global_index"] = self.global_start_index
        evidence["citation_label"] = "[reference:{}]".format(self.global_start_index)
        page["evidence"] = evidence
        page["evidence_id"] = evidence.get("evidence_id")
        self.added.append(page)
        self.global_start_index += 1
        return page


def test_evidence_verification_feedback_search_repair_pipeline_runs():
    article = (
        "# Report\n\n"
        "## Market Analysis\n"
        "AgC has a 90% market share and ROI reaches 200%.\n"
    )
    root_node_json = {
        "result": {
            "rubric_gap": {
                "dimensions": [],
                "missing_required": ["market_context"],
                "preferred_web_missing": ["competitors"],
            }
        }
    }
    graph = build_evidence_graph(
        ledger_items=[],
        article=article,
        root_node_json=root_node_json,
    )
    verification = verify_report_claims(article=article, ledger_items=[])
    quality_audit = {
        "section_citation_metrics": [
            {
                "title": "Market Analysis",
                "citation_count": 0,
                "char_count": 120,
            }
        ],
        "low_citation_sections": [
            {
                "title": "Market Analysis",
                "citation_count": 0,
                "char_count": 120,
            }
        ],
    }
    feedback = build_writer_feedback(
        claim_verification=verification,
        quality_audit=quality_audit,
        evidence_graph=graph,
        root_node_json=root_node_json,
    )
    memory = FakeMemory()

    def fake_search_client(query, topk):
        return [
            {
                "title": "Local KB: AgC market context",
                "url": "local-kb://agc-market.md",
                "summary": "AgC market analysis should compare vendors and avoid unsupported ROI figures.",
                "source": "agc-market.md",
                "chunk_index": 1,
            }
        ]

    search_report = run_search_repair(
        feedback,
        root_goal="AgC platform market report",
        memory=memory,
        language="en",
        execute_kb=True,
        search_client=fake_search_client,
        max_queries=2,
    )
    feedback = augment_writer_feedback_with_search_repair(feedback, search_report)
    ledger_items = [page["evidence"] for page in memory.added]

    def fake_repair(payload):
        assert payload["evidence"][0]["citation_label"] == "[reference:9]"
        return (
            "## Market Analysis\n"
            "AgC market analysis should compare vendors and mark ROI assumptions for validation. [reference:9]"
        )

    repaired, repair_report = run_writer_repair_loop(
        article=article,
        writer_feedback=feedback,
        ledger_items=ledger_items,
        repair_client=fake_repair,
        max_sections=1,
    )

    assert graph["summary"]["rubric_missing"] == ["market_context"]
    assert verification["summary"]["unsupported_count"] == 1
    assert search_report["summary"]["new_evidence_count"] == 1
    assert repair_report["repaired_section_count"] == 1
    assert "[reference:9]" in repaired
