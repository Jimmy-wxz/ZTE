from followup_test_utils import load_followup_module


intent_module = load_followup_module("intent")
classify_followup_intent = intent_module.classify_followup_intent


def test_followup_intent_detects_table_and_search_need():
    result = classify_followup_intent("在竞品分析章节补充一个市场对比表格")

    assert result["intent_type"] == "add_table"
    assert result["requires_search_repair"] is True
    assert result["target_section_hint"]


def test_followup_intent_detects_remove_unsupported_numbers():
    result = classify_followup_intent("删除没有证据支撑的 ROI 和成本数字")

    assert result["intent_type"] == "remove_unsupported"
    assert result["risk_level"] == "high"
    assert result["scope"] == "evidence_sensitive"
