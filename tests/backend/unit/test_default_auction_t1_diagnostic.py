import json

from backend.database import Base, engine
from backend.models import DefaultAuctionTrainingSample, ModelVersion
from backend.services.model_engine.default_auction_t1_diagnostic import (
    build_prediction_bucket_summary,
    describe_numeric,
    diagnose_t1_premium_model,
)


def test_describe_numeric_returns_percentiles():
    result = describe_numeric([1, 2, 3, 4, 5])

    assert result == {
        "count": 5,
        "min": 1.0,
        "p10": 1.4,
        "p25": 2.0,
        "avg": 3.0,
        "p50": 3.0,
        "p75": 4.0,
        "p90": 4.6,
        "max": 5.0,
    }


def test_build_prediction_bucket_summary_reports_hit_rate_lift_and_spread():
    result = build_prediction_bucket_summary(
        probabilities=[10, 20, 30, 40, 50],
        labels=[0, 0, 1, 1, 1],
        bucket_count=5,
    )

    assert result["baseline_rate"] == 0.6
    assert result["probability_spread"] == 40.0
    assert result["buckets"][0] == {
        "bucket": "bottom_1",
        "count": 1,
        "prob_min": 10.0,
        "prob_max": 10.0,
        "prob_avg": 10.0,
        "hit_rate": 0.0,
        "lift": -0.6,
    }
    assert result["buckets"][-1]["bucket"] == "top_1"
    assert result["buckets"][-1]["hit_rate"] == 1.0
    assert result["buckets"][-1]["lift"] == 0.4


def test_diagnose_t1_premium_model_reads_samples_and_flags_compressed_active_model(db, tmp_path):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(ModelVersion).delete()
    db.commit()

    for index, (label, source) in enumerate(
        [
            (0, "replay_backtest"),
            (1, "replay_backtest"),
            (1, "real_selected"),
            (0, "real_selected"),
        ],
        start=1,
    ):
        db.add(
            DefaultAuctionTrainingSample(
                trade_date=f"2026050{index}",
                ts_code=f"00000{index}.SZ",
                sample_source=source,
                strategy_name="default",
                feature_json=json.dumps({"auction_ratio": 5 + index}, ensure_ascii=False),
                label_t1_premium_success=label,
                t1_open_return=float(index),
                t1_high_return=float(index + 2),
                t1_close_return=float(index - 2),
            )
        )
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"fake")
    db.add(
        ModelVersion(
            model_name="default_auction_t1_premium_lgbm",
            version="flat_v1",
            model_path=str(model_path),
            is_active=1,
            model_metrics=json.dumps({"sample_count": 4, "auc": 0.55}, ensure_ascii=False),
        )
    )
    db.commit()

    result = diagnose_t1_premium_model(
        db,
        prediction_probabilities=[51.5, 51.7, 52.0, 52.2],
    )

    assert result["active_model"]["version"] == "flat_v1"
    assert result["current_samples"]["dedup_count"] == 4
    assert result["label_distribution"]["positive_rate"] == 0.5
    assert result["label_distribution_by_source"]["real_selected"]["positive_rate"] == 0.5
    assert result["prediction_diagnostics"]["distribution"]["min"] == 51.5
    assert "active_probability_spread_too_narrow" in result["findings"]


def test_diagnose_t1_premium_model_marks_accepted_rolling_window_as_intentional(db, tmp_path):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(ModelVersion).delete()
    db.commit()

    for index in range(10):
        db.add(
            DefaultAuctionTrainingSample(
                trade_date=f"202605{index + 1:02d}",
                ts_code=f"000{index:03d}.SZ",
                sample_source="replay_backtest",
                strategy_name="default",
                feature_json=json.dumps({"auction_ratio": 5 + index}, ensure_ascii=False),
                label_t1_premium_success=index % 2,
            )
        )
    model_path = tmp_path / "rolling.pkl"
    model_path.write_bytes(b"fake")
    db.add(
        ModelVersion(
            model_name="default_auction_t1_premium_lgbm",
            version="rolling_v1",
            train_start_date="20260507",
            train_end_date="20260510",
            model_path=str(model_path),
            is_active=1,
            model_metrics=json.dumps(
                {
                    "sample_count": 4,
                    "auc": 0.60,
                    "acceptance": {"accepted": True, "reject_reasons": []},
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()

    result = diagnose_t1_premium_model(
        db,
        prediction_probabilities=[42, 45, 48, 51, 54, 57, 60, 63, 66, 69],
    )

    assert "active_model_uses_recent_rolling_window" in result["findings"]
    assert "active_model_trained_on_stale_smaller_sample_set" not in result["findings"]
    assert result["recommendations"] == [
        "不要把问题归因于正负样本不均衡，优先检查标签口径和特征解释力"
    ]
