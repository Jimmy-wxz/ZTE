from evidence_test_utils import load_evidence_module


search_repair_module = load_evidence_module("search_repair")
build_search_repair_plan = search_repair_module.build_search_repair_plan
run_search_repair = search_repair_module.run_search_repair
augment_writer_feedback_with_search_repair = (
    search_repair_module.augment_writer_feedback_with_search_repair
)


class FakeMemory:
    def __init__(self):
        self.global_start_index = 5
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


def _feedback():
    return {
        "section_feedback": [
            {
                "section_title": "Market Analysis",
                "citation_count": 0,
                "unsupported_claim_count": 0,
                "partial_claim_count": 0,
            }
        ],
        "actions": [
            {
                "action_type": "supplement_missing_rubric_dimension",
                "severity": "high",
                "target_rubric_dimension": "market_context",
            },
            {
                "action_type": "supplement_web_context",
                "severity": "medium",
                "target_rubric_dimension": "competitors",
            },
        ],
        "summary": {"repair_needed": True},
    }


def test_search_repair_plan_targets_rubric_gaps():
    plan = build_search_repair_plan(
        _feedback(),
        root_goal="AgC platform market report",
        language="en",
        max_queries=5,
    )

    dimensions = {
        target["target_rubric_dimension"]
        for target in plan["targets"]
    }
    joined = "\n".join(plan["queries"]).lower()

    assert dimensions == {"market_context", "competitors"}
    assert "market" in joined
    assert "competitor" in joined
    assert plan["summary"]["web_required_count"] == 1


def test_search_repair_registers_kb_evidence_and_augments_feedback():
    memory = FakeMemory()

    def fake_search_client(query, topk):
        assert topk == 2
        return [
            {
                "title": "Local KB: AgC market",
                "url": "local-kb://agc-market.md",
                "summary": "AgC platform market evidence and vendor comparison context.",
                "source": "agc-market.md",
                "chunk_index": 3,
            }
        ]

    report = run_search_repair(
        _feedback(),
        root_goal="AgC platform market report",
        memory=memory,
        language="en",
        execute_kb=True,
        kb_topk=2,
        max_queries=2,
        search_client=fake_search_client,
    )
    augmented = augment_writer_feedback_with_search_repair(_feedback(), report)

    assert report["executed"] is True
    assert report["summary"]["new_evidence_count"] == 1
    assert report["kb_results"][0]["citation_label"] == "[reference:5]"
    assert len(memory.added) == 1
    assert augmented["search_repair_evidence_ids"] == report["new_evidence_ids"]
    assert any(
        action.get("action_type") == "minimal_section_rewrite"
        and action.get("target_section") == "Market Analysis"
        for action in augmented["actions"]
    )
