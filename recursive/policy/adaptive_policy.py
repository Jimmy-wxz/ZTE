# coding:utf8

import json
import math
import os
from datetime import datetime
from typing import Any, Dict, Optional

from .feature_extractor import extract_task_features


ENV_OVERRIDE_KEYS = {
    "kb_variant_topk": "WRITEHERE_KB_VARIANT_TOPK",
    "kb_rerank_candidate_limit": "WRITEHERE_KB_RERANK_CANDIDATES",
    "kb_rerank_cpu_candidates": "WRITEHERE_KB_RERANK_CPU_CANDIDATES",
    "kb_rerank_mode": "WRITEHERE_KB_RERANK_MODE",
    "kb_final_topk": "WRITEHERE_KB_FINAL_TOPK",
    "kb_diverse_per_source": "WRITEHERE_KB_DIVERSE_PER_SOURCE",
    "kb_web_fallback_coverage_threshold": "WRITEHERE_KB_WEB_FALLBACK_COVERAGE_THRESHOLD",
    "kb_web_force_supplement": "WRITEHERE_KB_WEB_FORCE_SUPPLEMENT",
    "max_search_queries": "WRITEHERE_MAX_SEARCH_QUERIES",
    "topk": "WRITEHERE_SEARCH_TOPK",
    "pk_quota": "WRITEHERE_SEARCH_PK_QUOTA",
    "select_quota": "WRITEHERE_SEARCH_SELECT_QUOTA",
    "llm_merge": "WRITEHERE_LLM_MERGE",
    "execute_retry_limit": "WRITEHERE_RETRY_LIMIT",
    "merge_retry_limit": "WRITEHERE_RETRY_LIMIT",
    "search_parse_retry_limit": "WRITEHERE_RETRY_LIMIT",
}


RUNTIME_CONTROL_ENV = {
    "enable_claim_verifier": "WRITEHERE_LLM_CLAIM_VERIFIER",
    "enable_search_repair": "WRITEHERE_SEARCH_REPAIR",
    "enable_repair_loop": "WRITEHERE_REPAIR_LOOP",
    "repair_max_sections": "WRITEHERE_REPAIR_MAX_SECTIONS",
}


MODE_SETTINGS = {
    "atom": {
        "kb_variant_topk": 3,
        "kb_final_topk": 4,
        "kb_rerank_candidate_limit": 12,
        "kb_rerank_cpu_candidates": 6,
        "kb_rerank_mode": "fast",
        "kb_diverse_per_source": 1,
        "kb_web_fallback_coverage_threshold": 0.0,
        "kb_web_force_supplement": False,
        "max_search_queries": 2,
        "topk": 8,
        "pk_quota": 6,
        "select_quota": 4,
        "llm_merge": False,
        "execute_retry_limit": 1,
        "merge_retry_limit": 1,
        "search_parse_retry_limit": 1,
        "enable_web": False,
        "enable_claim_verifier": False,
        "enable_search_repair": True,
        "enable_repair_loop": True,
        "repair_max_sections": 1,
    },
    "wide": {
        "kb_variant_topk": 4,
        "kb_final_topk": 8,
        "kb_rerank_candidate_limit": 24,
        "kb_rerank_cpu_candidates": 8,
        "kb_rerank_mode": "auto",
        "kb_diverse_per_source": 1,
        "kb_web_fallback_coverage_threshold": 0.60,
        "kb_web_force_supplement": False,
        "max_search_queries": 4,
        "topk": 12,
        "pk_quota": 12,
        "select_quota": 8,
        "llm_merge": "auto",
        "execute_retry_limit": 2,
        "merge_retry_limit": 2,
        "search_parse_retry_limit": 2,
        "enable_web": True,
        "enable_claim_verifier": False,
        "enable_search_repair": True,
        "enable_repair_loop": True,
        "repair_max_sections": 2,
    },
    "deep": {
        "kb_variant_topk": 6,
        "kb_final_topk": 10,
        "kb_rerank_candidate_limit": 48,
        "kb_rerank_cpu_candidates": 16,
        "kb_rerank_mode": "auto",
        "kb_diverse_per_source": 2,
        "kb_web_fallback_coverage_threshold": 0.68,
        "kb_web_force_supplement": True,
        "max_search_queries": 8,
        "topk": 20,
        "pk_quota": 18,
        "select_quota": 12,
        "llm_merge": "auto",
        "execute_retry_limit": 2,
        "merge_retry_limit": 2,
        "search_parse_retry_limit": 2,
        "enable_web": True,
        "enable_claim_verifier": True,
        "enable_search_repair": True,
        "enable_repair_loop": True,
        "repair_max_sections": 3,
    },
}


def build_policy_decision(
    prompt: str,
    config: Dict[str, Any] = None,
    history_store: Any = None,
    task_id: str = "",
    engine_backend: str = "",
    item: Dict[str, Any] = None,
    model_config: Dict[str, str] = None,
) -> Dict[str, Any]:
    """Build an explainable adaptive-policy decision for one report run."""
    config = config or {}
    model_config = model_config or {}
    features = extract_task_features(
        prompt=prompt,
        config=config,
        engine_backend=engine_backend,
        item=item,
    )
    history_summary = (
        history_store.summarize(features=features)
        if history_store is not None and hasattr(history_store, "summarize")
        else {"recent_count": 0, "matching_count": 0, "mode_stats": {}}
    )
    heuristic = _heuristic_recommendation(features, engine_backend)
    history_recommendation, history_adjustment = _apply_history_adjustment(
        heuristic, history_summary)
    recommendation, bandit_selection = _apply_bandit_selection(
        heuristic=heuristic,
        history_recommendation=history_recommendation,
        history_summary=history_summary,
        features=features,
    )
    recommendation["model_profile"] = _model_profile(
        recommendation["search_mode"], model_config)

    apply_requested = _env_bool("WRITEHERE_POLICY_APPLY", False)
    decision = {
        "version": "1.0",
        "policy_strategy": "heuristic_history_mean_bandit",
        "task_id": task_id or features.get("task_id", ""),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "features": features,
        "history_summary": history_summary,
        "heuristic_recommendation": heuristic,
        "history_adjustment": history_adjustment,
        "bandit_selection": bandit_selection,
        "recommendation": recommendation,
        "runtime_application_requested": apply_requested,
        "applied_to_runtime": False,
        "runtime_application_note": (
            "Decision is recorded only in this MVP and does not override "
            "runtime config yet."
        ),
    }
    return decision


def apply_policy_decision_to_runtime(
    config: Dict[str, Any],
    decision: Dict[str, Any],
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Apply a policy decision to one run config when explicitly requested."""
    environ = environ if environ is not None else os.environ
    decision = decision or {}
    application = {
        "requested": bool(decision.get("runtime_application_requested")),
        "applied": False,
        "applied_settings": {},
        "skipped_settings": {},
        "runtime_controls": {},
        "reason": "",
    }
    if not application["requested"]:
        application["reason"] = "WRITEHERE_POLICY_APPLY is disabled."
        decision["runtime_application"] = application
        decision["applied_to_runtime"] = False
        return application

    recommendation = decision.get("recommendation") or {}
    mode = recommendation.get("search_mode")
    settings = recommendation.get("settings") or {}
    execute_cfg = (
        config.setdefault("RETRIEVAL", {})
        .setdefault("execute", {})
    )

    for key, value in settings.items():
        if key in ("enable_web", "enable_claim_verifier", "enable_search_repair",
                   "enable_repair_loop", "repair_max_sections"):
            continue
        env_key = ENV_OVERRIDE_KEYS.get(key)
        if env_key and env_key in environ:
            application["skipped_settings"][key] = {
                "reason": "explicit environment override",
                "env": env_key,
                "current": execute_cfg.get(key),
            }
            continue
        execute_cfg[key] = value
        application["applied_settings"][key] = value

    if mode:
        execute_cfg["search_mode"] = mode
        execute_cfg["policy_search_mode_applied"] = True
        application["applied_settings"]["search_mode"] = mode
    execute_cfg["policy_enable_web"] = bool(recommendation.get("enable_web", True))
    execute_cfg["policy_runtime_controls"] = _runtime_controls(settings, environ)
    application["runtime_controls"] = execute_cfg["policy_runtime_controls"]

    application["applied"] = True
    application["reason"] = "policy decision applied to this run config"
    decision["runtime_application"] = application
    decision["applied_to_runtime"] = True
    decision["runtime_application_note"] = (
        "Decision was applied to this run config. Explicit environment "
        "overrides remain higher priority."
    )
    return application


def save_policy_decision(path: str, decision: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(decision, f, indent=2, ensure_ascii=False)


def _heuristic_recommendation(features: Dict[str, Any], engine_backend: str) -> Dict[str, Any]:
    forced = _normalize_forced_mode(os.environ.get("WRITEHERE_SEARCH_MODE"))
    if forced != "auto":
        mode = forced
        reason = "forced by WRITEHERE_SEARCH_MODE"
    else:
        family = features.get("task_family")
        complexity = float(features.get("complexity_score", 0.0) or 0.0)
        high_risk = int(features.get("high_risk_term_count", 0) or 0)
        if family in ("strategy_roadmap", "risk_security", "research_paper") or complexity >= 0.65:
            mode = "deep"
            reason = "high-complexity task or risk/research/strategy requirements"
        elif family == "market_competitor" or high_risk >= 2:
            mode = "wide"
            reason = "market, competitor, or quantitative context likely needs broader evidence"
        else:
            mode = "atom"
            reason = "focused technical task with limited external context needs"

    settings = dict(MODE_SETTINGS[mode])
    backend = str(engine_backend or "").lower()
    if backend in ("none", "kb", "knowledge_base", "local_kb"):
        settings["enable_web"] = False
    return {
        "search_mode": mode,
        "reason": reason,
        "settings": settings,
        "enable_web": bool(settings.get("enable_web")),
        "enable_claim_verifier": bool(settings.get("enable_claim_verifier")),
        "enable_search_repair": True,
        "enable_repair_loop": True,
    }


def _apply_history_adjustment(
    heuristic: Dict[str, Any],
    history_summary: Dict[str, Any],
) -> tuple:
    mode_stats = history_summary.get("mode_stats") or {}
    matching_count = int(history_summary.get("matching_count", 0) or 0)
    if matching_count < 3 or not mode_stats:
        return dict(heuristic), {
            "applied": False,
            "reason": "insufficient matching history",
        }

    best_mode = None
    best_reward = None
    for mode, stats in mode_stats.items():
        if stats.get("count", 0) < 2:
            continue
        reward = float(stats.get("avg_reward", 0.0) or 0.0)
        if best_reward is None or reward > best_reward:
            best_mode = mode
            best_reward = reward

    if not best_mode or best_mode == heuristic.get("search_mode"):
        return dict(heuristic), {
            "applied": False,
            "reason": "history agrees with heuristic or lacks stable winner",
        }

    adjusted = dict(heuristic)
    adjusted["search_mode"] = best_mode
    adjusted["settings"] = dict(MODE_SETTINGS.get(best_mode, heuristic.get("settings", {})))
    adjusted["enable_web"] = bool(adjusted["settings"].get("enable_web"))
    adjusted["enable_claim_verifier"] = bool(
        adjusted["settings"].get("enable_claim_verifier"))
    adjusted["reason"] = (
        "history-adjusted: mode {} had the best average reward for similar tasks"
        .format(best_mode)
    )
    return adjusted, {
        "applied": True,
        "reason": "selected best historical mode",
        "previous_mode": heuristic.get("search_mode"),
        "new_mode": best_mode,
        "avg_reward": round(best_reward or 0.0, 4),
    }


def _apply_bandit_selection(
    heuristic: Dict[str, Any],
    history_recommendation: Dict[str, Any],
    history_summary: Dict[str, Any],
    features: Dict[str, Any],
) -> tuple:
    enabled = _env_bool("WRITEHERE_POLICY_BANDIT", True)
    min_history = int(os.environ.get("WRITEHERE_POLICY_BANDIT_MIN_HISTORY", "3"))
    matching_count = int(history_summary.get("matching_count", 0) or 0)
    if not enabled:
        return dict(history_recommendation), {
            "enabled": False,
            "applied": False,
            "reason": "bandit disabled",
            "mode_scores": {},
        }
    if matching_count < min_history:
        return dict(history_recommendation), {
            "enabled": True,
            "applied": False,
            "reason": "insufficient matching history for bandit",
            "min_history": min_history,
            "matching_count": matching_count,
            "mode_scores": {},
        }

    mode_stats = history_summary.get("mode_stats") or {}
    mode_scores = _bandit_mode_scores(
        heuristic_mode=heuristic.get("search_mode", "atom"),
        history_mode=history_recommendation.get("search_mode", heuristic.get("search_mode", "atom")),
        mode_stats=mode_stats,
        matching_count=matching_count,
    )
    selected_mode = _select_bandit_mode(
        mode_scores=mode_scores,
        mode_stats=mode_stats,
        features=features,
        heuristic_mode=heuristic.get("search_mode", "atom"),
    )
    selected = dict(history_recommendation)
    selected["search_mode"] = selected_mode
    selected["settings"] = dict(MODE_SETTINGS.get(selected_mode, MODE_SETTINGS["wide"]))
    selected["enable_web"] = bool(selected["settings"].get("enable_web"))
    selected["enable_claim_verifier"] = bool(
        selected["settings"].get("enable_claim_verifier"))
    selected["enable_search_repair"] = bool(
        selected["settings"].get("enable_search_repair", True))
    selected["enable_repair_loop"] = bool(
        selected["settings"].get("enable_repair_loop", True))
    selected["reason"] = "hybrid heuristic + history mean + bandit selected {}".format(
        selected_mode)

    return selected, {
        "enabled": True,
        "applied": True,
        "algorithm": "weighted_ucb",
        "selected_mode": selected_mode,
        "previous_mode": history_recommendation.get("search_mode"),
        "matching_count": matching_count,
        "mode_scores": mode_scores,
        "reason": "selected highest hybrid bandit score",
    }


def _bandit_mode_scores(
    heuristic_mode: str,
    history_mode: str,
    mode_stats: Dict[str, Dict[str, Any]],
    matching_count: int,
) -> Dict[str, Dict[str, float]]:
    heuristic_weight = float(os.environ.get("WRITEHERE_POLICY_HEURISTIC_WEIGHT", "0.35"))
    history_weight = float(os.environ.get("WRITEHERE_POLICY_HISTORY_WEIGHT", "0.65"))
    exploration = float(os.environ.get("WRITEHERE_POLICY_BANDIT_EXPLORATION", "8.0"))
    neutral_reward = float(os.environ.get("WRITEHERE_POLICY_NEUTRAL_REWARD", "55.0"))
    total = max(1, int(matching_count or 0))
    scores = {}
    for mode in ("atom", "wide", "deep"):
        stats = mode_stats.get(mode) or {}
        count = int(stats.get("count", 0) or 0)
        avg_reward = float(stats.get("avg_reward", neutral_reward) or neutral_reward)
        heuristic_score = _heuristic_prior_score(mode, heuristic_mode, history_mode)
        exploration_bonus = exploration * math.sqrt(
            math.log(total + 1.0) / max(1.0, count + 1.0))
        final_score = (
            heuristic_weight * heuristic_score
            + history_weight * avg_reward
            + exploration_bonus
        )
        scores[mode] = {
            "count": count,
            "avg_reward": round(avg_reward, 4),
            "heuristic_prior": round(heuristic_score, 4),
            "exploration_bonus": round(exploration_bonus, 4),
            "score": round(final_score, 4),
        }
    return scores


def _select_bandit_mode(
    mode_scores: Dict[str, Dict[str, float]],
    mode_stats: Dict[str, Dict[str, Any]],
    features: Dict[str, Any],
    heuristic_mode: str,
) -> str:
    epsilon = float(os.environ.get("WRITEHERE_POLICY_BANDIT_EPSILON", "0.0"))
    if epsilon > 0.0:
        seed = "{}:{}:{}".format(
            features.get("prompt_hash", ""),
            features.get("task_family", ""),
            sum((stats.get("count", 0) or 0) for stats in mode_stats.values()),
        )
        if _deterministic_unit(seed) < min(1.0, max(0.0, epsilon)):
            return _least_tried_mode(mode_stats, heuristic_mode)

    ordered = sorted(
        mode_scores.items(),
        key=lambda item: (
            -float(item[1].get("score", 0.0) or 0.0),
            _mode_tie_breaker(item[0], heuristic_mode),
        ),
    )
    return ordered[0][0] if ordered else heuristic_mode


def _heuristic_prior_score(mode: str, heuristic_mode: str, history_mode: str) -> float:
    if mode == heuristic_mode:
        return 76.0
    if mode == history_mode:
        return 68.0
    if heuristic_mode == "atom" and mode == "wide":
        return 58.0
    if heuristic_mode == "wide" and mode in ("atom", "deep"):
        return 62.0
    if heuristic_mode == "deep" and mode == "wide":
        return 60.0
    return 48.0


def _least_tried_mode(mode_stats: Dict[str, Dict[str, Any]], heuristic_mode: str) -> str:
    ordered = sorted(
        ("atom", "wide", "deep"),
        key=lambda mode: (
            int((mode_stats.get(mode) or {}).get("count", 0) or 0),
            _mode_tie_breaker(mode, heuristic_mode),
        ),
    )
    return ordered[0]


def _mode_tie_breaker(mode: str, heuristic_mode: str) -> int:
    if mode == heuristic_mode:
        return 0
    order = {"wide": 1, "atom": 2, "deep": 3}
    if heuristic_mode == "deep":
        order = {"deep": 0, "wide": 1, "atom": 2}
    elif heuristic_mode == "atom":
        order = {"atom": 0, "wide": 1, "deep": 2}
    return order.get(mode, 9)


def _deterministic_unit(seed: str) -> float:
    import hashlib

    digest = hashlib.sha1(str(seed).encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def _model_profile(mode: str, model_config: Dict[str, str]) -> Dict[str, str]:
    fast_model = model_config.get("fast_model", "")
    writer_model = model_config.get("writer_model", fast_model)
    reasoner_model = model_config.get("reasoner_model", fast_model)
    search_model = model_config.get("search_model", fast_model)
    if mode == "atom":
        return {
            "planning": fast_model,
            "search": fast_model,
            "writer": fast_model,
            "reasoner": fast_model,
        }
    if mode == "wide":
        return {
            "planning": fast_model,
            "search": search_model or fast_model,
            "writer": writer_model,
            "reasoner": fast_model,
        }
    return {
        "planning": fast_model,
        "search": search_model or fast_model,
        "writer": writer_model,
        "reasoner": reasoner_model,
    }


def _normalize_forced_mode(value: Optional[str]) -> str:
    mode = str(value or "auto").strip().lower()
    return mode if mode in ("atom", "wide", "deep") else "auto"


def _runtime_controls(settings: Dict[str, Any], environ: Dict[str, str]) -> Dict[str, Any]:
    controls = {
        "enable_claim_verifier": bool(settings.get("enable_claim_verifier", False)),
        "enable_search_repair": bool(settings.get("enable_search_repair", True)),
        "enable_repair_loop": bool(settings.get("enable_repair_loop", True)),
        "repair_max_sections": int(settings.get("repair_max_sections", 2) or 2),
    }
    for key, env_key in RUNTIME_CONTROL_ENV.items():
        if env_key not in environ:
            continue
        if key == "repair_max_sections":
            try:
                controls[key] = int(environ.get(env_key))
            except Exception:
                pass
        else:
            controls[key] = str(environ.get(env_key)).strip().lower() not in (
                "0", "false", "no", "off", "disable", "disabled")
    return controls


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() not in (
        "0", "false", "no", "off", "disable", "disabled")
