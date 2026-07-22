import tempfile
import os
from pathlib import Path

from policy_test_utils import load_policy_module


history_module = load_policy_module("history_store")
adaptive_module = load_policy_module("adaptive_policy")
feature_module = load_policy_module("feature_extractor")

HistoryStore = history_module.HistoryStore
apply_policy_decision_to_runtime = adaptive_module.apply_policy_decision_to_runtime
build_policy_decision = adaptive_module.build_policy_decision
extract_task_features = feature_module.extract_task_features


def test_policy_decision_recommends_wide_for_market_competitor_report():
    decision = build_policy_decision(
        prompt="Write a market and competitor report for an enterprise AI agent platform.",
        config={"language": "en"},
        engine_backend="google",
        model_config={"fast_model": "deepseek-chat", "writer_model": "deepseek-chat"},
    )

    assert decision["features"]["task_family"] == "market_competitor"
    assert decision["recommendation"]["search_mode"] == "wide"
    assert decision["recommendation"]["enable_web"] is True


def test_policy_decision_recommends_deep_for_strategy_risk_tasks():
    decision = build_policy_decision(
        prompt="Build an implementation roadmap, governance strategy, security risk analysis, and ROI estimate.",
        config={"language": "en"},
        engine_backend="google",
        model_config={"fast_model": "deepseek-chat"},
    )

    assert decision["recommendation"]["search_mode"] == "deep"
    assert decision["recommendation"]["enable_claim_verifier"] is True


def test_policy_decision_can_adjust_from_history():
    with tempfile.TemporaryDirectory() as temp_dir:
        store = HistoryStore(str(Path(temp_dir) / "history.jsonl"))
        for task_id, mode, reward in [
            ("a", "wide", 40),
            ("b", "deep", 82),
            ("c", "deep", 85),
        ]:
            store.append({
                "features": {
                    "language": "en",
                    "task_family": "market_competitor",
                },
                "decision": {
                    "recommended_search_mode": mode,
                },
                "outcome": {
                    "reward": reward,
                    "quality_score": reward,
                    "total_duration_seconds": 100,
                },
                "task_id": task_id,
            })

        decision = build_policy_decision(
            prompt="Write a market competitor report for AIOps.",
            history_store=store,
            engine_backend="google",
        )

        assert decision["heuristic_recommendation"]["search_mode"] == "wide"
        assert decision["history_adjustment"]["applied"] is True
        assert decision["bandit_selection"]["applied"] is True
        assert decision["bandit_selection"]["algorithm"] == "weighted_ucb"
        assert decision["recommendation"]["search_mode"] == "deep"


def test_policy_bandit_uses_exploration_bonus_for_undertried_mode():
    with tempfile.TemporaryDirectory() as temp_dir:
        store = HistoryStore(str(Path(temp_dir) / "history.jsonl"))
        for task_id, mode, reward in [
            ("a", "atom", 60),
            ("b", "wide", 65),
            ("c", "wide", 66),
            ("d", "deep", 67),
            ("e", "deep", 68),
        ]:
            store.append({
                "features": {
                    "language": "en",
                    "task_family": "market_competitor",
                },
                "decision": {"recommended_search_mode": mode},
                "outcome": {
                    "reward": reward,
                    "quality_score": reward,
                    "total_duration_seconds": 100,
                },
            })

        old = os.environ.get("WRITEHERE_POLICY_BANDIT_EXPLORATION")
        os.environ["WRITEHERE_POLICY_BANDIT_EXPLORATION"] = "30"
        try:
            decision = build_policy_decision(
                prompt="Write a market competitor report for AIOps.",
                history_store=store,
                engine_backend="google",
            )
        finally:
            if old is None:
                os.environ.pop("WRITEHERE_POLICY_BANDIT_EXPLORATION", None)
            else:
                os.environ["WRITEHERE_POLICY_BANDIT_EXPLORATION"] = old

        scores = decision["bandit_selection"]["mode_scores"]
        assert decision["bandit_selection"]["applied"] is True
        assert scores["atom"]["exploration_bonus"] > scores["wide"]["exploration_bonus"]
        assert "heuristic_history_mean_bandit" == decision["policy_strategy"]


def test_policy_bandit_epsilon_explores_least_tried_mode():
    with tempfile.TemporaryDirectory() as temp_dir:
        store = HistoryStore(str(Path(temp_dir) / "history.jsonl"))
        for task_id, mode, reward in [
            ("a", "wide", 80),
            ("b", "wide", 82),
            ("c", "deep", 81),
        ]:
            store.append({
                "features": {
                    "language": "en",
                    "task_family": "market_competitor",
                },
                "decision": {"recommended_search_mode": mode},
                "outcome": {
                    "reward": reward,
                    "quality_score": reward,
                    "total_duration_seconds": 100,
                },
            })

        old = os.environ.get("WRITEHERE_POLICY_BANDIT_EPSILON")
        os.environ["WRITEHERE_POLICY_BANDIT_EPSILON"] = "1"
        try:
            decision = build_policy_decision(
                prompt="Write a market competitor report for AIOps.",
                history_store=store,
                engine_backend="google",
            )
        finally:
            if old is None:
                os.environ.pop("WRITEHERE_POLICY_BANDIT_EPSILON", None)
            else:
                os.environ["WRITEHERE_POLICY_BANDIT_EPSILON"] = old

        assert decision["bandit_selection"]["applied"] is True
        assert decision["bandit_selection"]["selected_mode"] == "atom"
        assert decision["recommendation"]["search_mode"] == "atom"


def test_feature_extractor_detects_high_risk_terms():
    features = extract_task_features(
        "Estimate ROI, cost, market size, and growth forecast for the platform."
    )

    assert features["high_risk_term_count"] >= 4
    assert features["number_count"] == 0


def test_policy_application_updates_runtime_config_when_requested():
    config = {
        "RETRIEVAL": {
            "execute": {
                "search_mode": "auto",
                "kb_final_topk": 5,
                "max_search_queries": 6,
            }
        }
    }
    decision = build_policy_decision(
        prompt="Build a governance strategy roadmap and security risk report.",
        engine_backend="google",
        model_config={"fast_model": "deepseek-chat"},
    )
    decision["runtime_application_requested"] = True

    application = apply_policy_decision_to_runtime(
        config,
        decision,
        environ={"WRITEHERE_POLICY_APPLY": "1"},
    )

    execute_cfg = config["RETRIEVAL"]["execute"]
    assert application["applied"] is True
    assert decision["applied_to_runtime"] is True
    assert execute_cfg["search_mode"] == "deep"
    assert execute_cfg["kb_final_topk"] == 10
    assert execute_cfg["policy_runtime_controls"]["enable_claim_verifier"] is True
    assert execute_cfg["policy_runtime_controls"]["repair_max_sections"] == 3


def test_policy_application_respects_explicit_env_overrides():
    config = {
        "RETRIEVAL": {
            "execute": {
                "search_mode": "auto",
                "kb_final_topk": 5,
            }
        }
    }
    decision = build_policy_decision(
        prompt="Write a market competitor report.",
        engine_backend="google",
    )
    decision["runtime_application_requested"] = True

    application = apply_policy_decision_to_runtime(
        config,
        decision,
        environ={
            "WRITEHERE_POLICY_APPLY": "1",
            "WRITEHERE_KB_FINAL_TOPK": "6",
            "WRITEHERE_REPAIR_MAX_SECTIONS": "1",
        },
    )

    assert application["applied"] is True
    assert config["RETRIEVAL"]["execute"]["kb_final_topk"] == 5
    assert "kb_final_topk" in application["skipped_settings"]
    assert config["RETRIEVAL"]["execute"]["policy_runtime_controls"]["repair_max_sections"] == 1


def test_policy_application_noops_when_not_requested():
    config = {
        "RETRIEVAL": {
            "execute": {
                "search_mode": "auto",
                "kb_final_topk": 5,
            }
        }
    }
    decision = build_policy_decision(
        prompt="Write a market competitor report.",
        engine_backend="google",
    )

    application = apply_policy_decision_to_runtime(config, decision, environ={})

    assert application["applied"] is False
    assert decision["applied_to_runtime"] is False
    assert config["RETRIEVAL"]["execute"]["search_mode"] == "auto"
