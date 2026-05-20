import json

from backend.services.model_engine.default_auction_model_evaluator import (
    AcceptanceGate,
    TARGET_GATES,
    evaluate_topk,
    judge_target_acceptance,
)


def test_evaluate_topk_outputs_baseline_and_lift():
    rows = [
        {"trade_date": "20260501", "prob": 0.9, "label": 1},
        {"trade_date": "20260501", "prob": 0.8, "label": 1},
        {"trade_date": "20260501", "prob": 0.7, "label": 0},
        {"trade_date": "20260502", "prob": 0.9, "label": 1},
        {"trade_date": "20260502", "prob": 0.8, "label": 0},
        {"trade_date": "20260502", "prob": 0.7, "label": 0},
    ]

    result = evaluate_topk(rows)

    assert result["sample_count"] == 6
    assert result["daily_count"] == 2
    assert result["baseline_rate"] == 0.5
    assert result["top1_rate"] == 1.0
    assert result["top3_rate"] == 0.5
    assert result["top5_rate"] == 0.5
    assert result["top1_lift"] == 0.5
    assert result["top3_lift"] == 0.0
    assert result["top5_lift"] == 0.0
    assert result["topk_positive_count"] == 3
    assert result["top5_sample_count"] == 6


def test_evaluate_topk_filters_unknown_labels_before_ranking():
    rows = [
        {"trade_date": "20260501", "prob": 0.99, "label": None},
        {"trade_date": "20260501", "prob": 0.80, "label": 1},
        {"trade_date": "20260501", "prob": 0.70, "label": 0},
        {"trade_date": "20260502", "prob": 0.95, "label": None},
        {"trade_date": "20260502", "prob": "bad-number", "label": 0},
        {"trade_date": "20260502", "prob": 0.60, "label": 1},
    ]

    result = evaluate_topk(rows)

    assert result["sample_count"] == 4
    assert result["unknown_label_count"] == 2
    assert result["baseline_rate"] == 0.5
    assert result["top1_rate"] == 1.0
    assert result["top5_sample_count"] == 4
    assert result["topk_positive_count"] == 2


def test_evaluate_topk_empty_rows_returns_stable_json_serializable_metrics():
    result = evaluate_topk([])

    assert result == {
        "sample_count": 0,
        "unknown_label_count": 0,
        "invalid_trade_date_count": 0,
        "daily_count": 0,
        "baseline_rate": 0.0,
        "top1_rate": 0.0,
        "top3_rate": 0.0,
        "top5_rate": 0.0,
        "top1_lift": 0.0,
        "top3_lift": 0.0,
        "top5_lift": 0.0,
        "top1_sample_count": 0,
        "top3_sample_count": 0,
        "top5_sample_count": 0,
        "topk_positive_count": 0,
    }
    json.dumps(result, allow_nan=False)


def test_evaluate_topk_filters_missing_trade_date_and_keeps_strict_json():
    rows = [
        {"trade_date": "", "prob": 0.99, "label": 1},
        {"trade_date": None, "prob": 0.98, "label": 1},
        {"prob": 0.97, "label": 1},
        {"trade_date": "20260501", "prob": 0.80, "label": 0},
        {"trade_date": "20260501", "prob": 0.70, "label": 1},
    ]

    result = evaluate_topk(rows)

    assert result["sample_count"] == 2
    assert result["invalid_trade_date_count"] == 3
    assert result["daily_count"] == 1
    assert result["baseline_rate"] == 0.5
    assert result["top1_rate"] == 0.0
    json.dumps(result, allow_nan=False)


def test_evaluate_topk_all_unknown_labels_returns_json_safe_metrics():
    rows = [
        {"trade_date": "20260501", "prob": 0.9, "label": None},
        {"trade_date": "20260502", "prob": 0.8, "label": ""},
        {"trade_date": "20260503", "prob": 0.7, "label": "bad-label"},
    ]

    result = evaluate_topk(rows)

    assert result["sample_count"] == 0
    assert result["unknown_label_count"] == 3
    assert result["invalid_trade_date_count"] == 0
    json.dumps(result, allow_nan=False)


def test_evaluate_topk_bad_nan_and_inf_prob_are_json_safe():
    rows = [
        {"trade_date": "20260501", "prob": float("nan"), "label": 1},
        {"trade_date": "20260501", "prob": float("inf"), "label": 0},
        {"trade_date": "20260501", "prob": "-inf", "label": 1},
        {"trade_date": "20260501", "prob": "bad-number", "label": 0},
    ]

    result = evaluate_topk(rows)

    assert result["sample_count"] == 4
    assert result["top5_sample_count"] == 4
    assert result["topk_positive_count"] == 2
    json.dumps(result, allow_nan=False)


def test_judge_target_acceptance_rejects_when_topk_lift_too_low():
    metrics = {
        "baseline_rate": 0.4,
        "top3_rate": 0.42,
        "top5_rate": 0.43,
        "topk_positive_count": 50,
        "auc": 0.6,
    }
    gate = AcceptanceGate(top3_lift=0.10, top5_lift=0.06, min_topk_positive_count=30, min_auc=0.55)

    result = judge_target_acceptance(metrics, gate)

    assert result["accepted"] is False
    assert "top3_lift_below_threshold" in result["reject_reasons"]
    assert "top5_lift_below_threshold" in result["reject_reasons"]
    assert result["gate"] == gate.to_dict()


def test_judge_target_acceptance_checks_positive_count_and_auc():
    metrics = {
        "baseline_rate": 0.2,
        "top3_rate": 0.5,
        "top5_rate": 0.4,
        "topk_positive_count": 2,
        "auc": None,
    }
    gate = AcceptanceGate(top3_lift=0.10, top5_lift=0.06, min_topk_positive_count=3, min_auc=0.55)

    result = judge_target_acceptance(metrics, gate)

    assert result["accepted"] is False
    assert "topk_positive_count_below_threshold" in result["reject_reasons"]
    assert "auc_below_threshold" in result["reject_reasons"]


def test_judge_target_acceptance_rejects_compressed_probability_even_when_topk_passes():
    metrics = {
        "baseline_rate": 0.5,
        "top3_lift": 0.16,
        "top5_lift": 0.12,
        "topk_positive_count": 40,
        "auc": 0.62,
        "probability_spread": 1.62,
        "trained_tree_count": 1,
    }
    gate = AcceptanceGate(
        top3_lift=0.10,
        top5_lift=0.06,
        min_topk_positive_count=25,
        min_auc=0.55,
        min_probability_spread=5.0,
        min_trained_tree_count=5,
    )

    result = judge_target_acceptance(metrics, gate)

    assert result["accepted"] is False
    assert "probability_spread_below_threshold" in result["reject_reasons"]
    assert "trained_tree_count_below_threshold" in result["reject_reasons"]


def test_judge_target_acceptance_accepts_exact_fallback_lift_threshold():
    metrics = {
        "baseline_rate": 0.55,
        "top3_rate": 0.63,
        "top5_rate": 0.60,
        "topk_positive_count": 30,
        "auc": 0.55,
    }
    gate = AcceptanceGate(top3_lift=0.08, top5_lift=0.05, min_topk_positive_count=30, min_auc=0.55)

    result = judge_target_acceptance(metrics, gate)

    assert result["accepted"] is True
    assert result["reject_reasons"] == []


def test_target_gates_contains_three_default_auction_targets():
    assert set(TARGET_GATES) == {
        "default_auction_t0_limit_lgbm",
        "default_auction_t1_premium_lgbm",
        "default_auction_t1_continue_lgbm",
    }
