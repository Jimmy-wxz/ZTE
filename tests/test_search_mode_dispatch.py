import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_search_mode_module():
    spec = importlib.util.spec_from_file_location(
        "search_mode_under_test",
        ROOT / "recursive" / "search" / "mode.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mode_module = load_search_mode_module()


def test_atom_mode_for_simple_technical_lookup():
    profile = mode_module.classify_search_mode("Explain what IAST is and its core principle.")

    assert profile.mode == "atom"
    assert profile.settings["kb_final_topk"] == 4
    assert profile.settings["kb_rerank_mode"] == "fast"


def test_wide_mode_for_market_and_competitor_report():
    profile = mode_module.classify_search_mode(
        "选择一个知识库中的技术进行介绍和竞品分析，形成市场报告"
    )

    assert profile.mode == "wide"
    assert profile.settings["max_search_queries"] == 4
    assert profile.settings["pk_quota"] == 12


def test_root_context_does_not_override_atomic_node():
    profile = mode_module.classify_search_mode(
        "Explain what IAST is.",
        root_question="形成 IAST 技术市场报告，包含竞品分析、趋势和商业机会",
    )

    assert profile.mode == "atom"


def test_deep_mode_for_strategy_and_research_plan():
    profile = mode_module.classify_search_mode(
        "围绕 RAG 系统设计技术创新路线、风险、实施方案和论文实验框架，形成完整研究规划",
        task_length=1200,
    )

    assert profile.mode == "deep"
    assert profile.settings["kb_web_force_supplement"] is True
    assert profile.settings["kb_final_topk"] == 8


def test_forced_mode_and_env_overrides_win():
    profile = mode_module.classify_search_mode(
        "Explain IAST",
        forced_mode="deep",
    )
    tuned = mode_module.apply_search_mode_overrides(
        {"kb_final_topk": 5, "max_search_queries": 6},
        profile,
        environ={"WRITEHERE_KB_FINAL_TOPK": "5"},
    )

    assert profile.mode == "deep"
    assert profile.forced is True
    assert tuned["kb_final_topk"] == 5
    assert tuned["max_search_queries"] == 6
    assert tuned["search_mode"] == "deep"
