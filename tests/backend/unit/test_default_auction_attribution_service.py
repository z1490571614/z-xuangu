from backend.services.model_engine.default_auction_attribution_service import (
    build_bucket_report,
    build_feature_quality_report,
    build_single_prediction_attribution,
    build_training_attribution,
)


def test_feature_quality_report_excludes_high_missing_and_constant_features():
    rows = [
        {"auction_ratio": 8.1, "seal_rate": 80, "empty_feature": None, "constant_feature": 1, "label": 1},
        {"auction_ratio": 12.0, "seal_rate": 90, "empty_feature": None, "constant_feature": 1, "label": 0},
        {"auction_ratio": 15.0, "seal_rate": None, "empty_feature": None, "constant_feature": 1, "label": 1},
    ]

    report = build_feature_quality_report(rows, ["auction_ratio", "seal_rate", "empty_feature", "constant_feature"])

    assert "auction_ratio" in report["usable_features"]
    assert "seal_rate" in report["usable_features"]
    assert "empty_feature" in report["dropped_features"]
    assert "constant_feature" in report["dropped_features"]
    assert report["features"]["empty_feature"]["missing_rate"] == 1.0
    assert report["features"]["constant_feature"]["reason"] == "constant"


def test_feature_quality_report_ignores_known_string_features_when_auto_detecting():
    rows = [
        {"auction_ratio": "8.1", "score_level": "A", "lu_tag": "算力", "lu_status": "涨停", "label": 1},
        {"auction_ratio": "bad-number", "score_level": "B", "lu_tag": "算力", "lu_status": "炸板", "label": 0},
        {"auction_ratio": 12.0, "score_level": "A", "lu_tag": "机器人", "lu_status": "涨停", "label": 1},
    ]

    report = build_feature_quality_report(rows)

    assert "auction_ratio" in report["usable_features"]
    assert "score_level" in report["ignored_features"]
    assert "lu_tag" in report["ignored_features"]
    assert "lu_status" in report["ignored_features"]
    assert report["features"]["score_level"]["type"] == "categorical"
    assert report["features"]["auction_ratio"]["invalid_count"] == 1


def test_feature_quality_report_empty_rows_returns_stable_structure():
    report = build_feature_quality_report([], ["auction_ratio"])

    assert report["sample_count"] == 0
    assert report["usable_features"] == []
    assert report["dropped_features"] == ["auction_ratio"]
    assert report["features"]["auction_ratio"]["missing_rate"] == 1.0


def test_feature_quality_report_includes_source_label_and_date_coverage():
    rows = [
        {"trade_date": "20260508", "sample_source": "real_selected", "auction_ratio": 8.1, "label": 1},
        {"trade_date": "20260508", "sample_source": "replay_backtest", "auction_ratio": 12.0, "label": 0},
        {"trade_date": "20260509", "sample_source": "replay_backtest", "auction_ratio": 60.0, "label": 1},
    ]

    report = build_feature_quality_report(rows, ["auction_ratio"])

    assert report["source_mix_ratio"] == {"real_selected": 0.3333, "replay_backtest": 0.6667}
    assert report["positive_negative_ratio"] == {"positive": 2, "negative": 1, "positive_rate": 0.6667}
    assert report["coverage_by_date"] == {"20260508": 2, "20260509": 1}
    assert report["features"]["auction_ratio"]["outlier_count"] == 1
    assert report["features"]["auction_ratio"]["outlier_rate"] == 0.3333


def test_bucket_report_outputs_lift_for_auction_ratio():
    rows = [
        {"auction_ratio": 6.0, "label": 0, "prob": 0.2},
        {"auction_ratio": 10.0, "label": 1, "prob": 0.9},
        {"auction_ratio": 12.0, "label": 1, "prob": 0.8},
        {"auction_ratio": 35.0, "label": 0, "prob": 0.1},
    ]

    report = build_bucket_report(rows, label_key="label", prob_key="prob")

    auction_buckets = [item for item in report if item["feature_name"] == "auction_ratio"]
    assert any(item["bucket"] == "8-15" and item["positive_rate"] == 1.0 for item in auction_buckets)
    assert all("bucket_top5_positive_rate" in item for item in auction_buckets)
    assert all("topk_positive_rate" in item for item in auction_buckets)


def test_bucket_report_filters_unknown_labels_and_invalid_numbers():
    rows = [
        {"auction_ratio": 10.0, "label": 1, "prob": 0.9},
        {"auction_ratio": 12.0, "label": None, "prob": 0.8},
        {"auction_ratio": "not-a-number", "label": 0, "prob": 0.1},
    ]

    report = build_bucket_report(rows, feature_names=["auction_ratio"], label_key="label", prob_key="prob")

    assert report == [
        {
            "feature_name": "auction_ratio",
            "bucket": "8-15",
            "sample_count": 1,
            "positive_count": 1,
            "positive_rate": 1.0,
            "baseline_rate": 0.5,
            "lift": 0.5,
            "bucket_top5_positive_rate": 1.0,
            "topk_positive_rate": 1.0,
            "conclusion": "高于基准",
        }
    ]


def test_bucket_report_auction_ratio_boundaries_do_not_put_negative_in_first_bucket():
    rows = [
        {"auction_ratio": -1, "label": 1, "prob": 0.9},
        {"auction_ratio": 7.99, "label": 0, "prob": 0.8},
        {"auction_ratio": 8, "label": 1, "prob": 0.7},
        {"auction_ratio": 15, "label": 1, "prob": 0.6},
        {"auction_ratio": 30, "label": 0, "prob": 0.5},
    ]

    report = build_bucket_report(rows, feature_names=["auction_ratio"], label_key="label", prob_key="prob")

    buckets = {item["bucket"]: item for item in report}
    assert set(buckets) == {"<8", "8-15", "15-30", "30+"}
    assert buckets["<8"]["sample_count"] == 1
    assert buckets["8-15"]["sample_count"] == 1
    assert buckets["15-30"]["sample_count"] == 1
    assert buckets["30+"]["sample_count"] == 1
    assert all(item["bucket"] != "invalid" for item in report)


def test_training_attribution_summarizes_success_and_failure():
    attribution = build_training_attribution(
        feature_importance={"auction_ratio": 10, "seal_rate": 0},
        bucket_report=[{"feature_name": "auction_ratio", "bucket": "8-15", "lift": 0.2}],
        reject_reasons=["top3_lift_below_threshold"],
    )

    assert attribution["top_positive_features"][0] == "auction_ratio"
    assert "seal_rate" in attribution["noise_features"]
    assert attribution["best_buckets"][0]["bucket"] == "8-15"
    assert "top3_lift_below_threshold" in attribution["failure_reasons"]
    assert "Top3提升不足" in attribution["failure_summary"]


def test_single_prediction_attribution_splits_positive_negative_and_bucket_explanations():
    result = build_single_prediction_attribution(
        probability=72.5,
        model_version="v1",
        features={"auction_ratio": 10.0, "auction_turnover_rate": 12.0, "seal_rate": 85},
        feature_contributions={"auction_ratio": 0.32, "auction_turnover_rate": -0.18, "seal_rate": 0.0},
        bucket_report=[
            {
                "feature_name": "auction_ratio",
                "bucket": "8-15",
                "lift": 0.2,
                "conclusion": "高于基准",
            },
            {
                "feature_name": "auction_turnover_rate",
                "bucket": "10+",
                "lift": -0.1,
                "conclusion": "不高于基准",
            },
        ],
        data_quality_warnings=["auction_turnover_rate_outlier"],
    )

    assert result["probability"] == 72.5
    assert result["model_version"] == "v1"
    assert any("auction_ratio" in item for item in result["positive_factors"])
    assert any("auction_turnover_rate" in item for item in result["negative_factors"])
    assert any("seal_rate" in item for item in result["neutral_factors"])
    assert result["feature_contributions"]["auction_ratio"] == 0.32
    assert len(result["bucket_explanations"]) == 2
    assert result["data_quality_warnings"] == ["auction_turnover_rate_outlier"]
