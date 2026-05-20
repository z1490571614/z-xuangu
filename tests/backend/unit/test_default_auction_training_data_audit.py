import json

from backend.database import Base, engine
from backend.models import DefaultAuctionTrainingSample
from backend.services.model_engine.default_auction_training_data_audit import (
    REQUIRED_DEFAULT_AUCTION_FEATURES,
    TrainingDataAuditConfig,
    audit_default_auction_training_data,
)


def _clear_training_samples(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.commit()


def _sample(
    trade_date,
    ts_code,
    sample_source="replay_backtest",
    features=None,
    t0=1,
    t1_premium=1,
    t1_continue=0,
):
    feature_json = {key: 1 for key in REQUIRED_DEFAULT_AUCTION_FEATURES}
    feature_json.update(features or {})
    return DefaultAuctionTrainingSample(
        trade_date=trade_date,
        ts_code=ts_code,
        name="测试股",
        strategy_name="default",
        strategy_version="default_auction_v2",
        sample_source=sample_source,
        replay_source="stock_auction_open" if sample_source == "replay_backtest" else None,
        auction_source="stock_auction_open",
        auction_ratio_unit="percent",
        auction_turnover_rate_basis="free_float",
        feature_snapshot_time=f"{trade_date}T09:25:00",
        feature_json=json.dumps(feature_json, ensure_ascii=False),
        label_t0_limit_success=t0,
        label_t1_premium_success=t1_premium,
        label_t1_continue_limit=t1_continue,
    )


def test_training_data_audit_passes_complete_default_auction_samples(db):
    _clear_training_samples(db)
    db.add_all(
        [
            _sample("20260506", "000001.SZ"),
            _sample("20260507", "600001.SH"),
            _sample("20260507", "000002.SZ", sample_source="real_selected"),
        ]
    )
    db.commit()

    result = audit_default_auction_training_data(
        db,
        TrainingDataAuditConfig(
            min_replay_days=2,
            min_replay_samples=2,
            max_replay_avg_per_day=15,
            require_replay_validation=False,
        ),
    )

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["sample_summary"]["total_count"] == 3
    assert result["sample_summary"]["by_source"]["replay_backtest"]["count"] == 2
    assert result["feature_missing_counts"]["seal_rate"] == 0
    assert result["label_coverage"]["label_t0_limit_success"]["missing_count"] == 0


def test_training_data_audit_fails_missing_features_non_a_share_and_bloated_replay(db):
    _clear_training_samples(db)
    db.add_all(
        [
            _sample("20260506", "000001.SZ", features={"seal_rate": None}),
            _sample("20260506", "HK0001.HK"),
            _sample("20260506", "600001.SH"),
            _sample("20260506", "600002.SH"),
        ]
    )
    db.commit()

    result = audit_default_auction_training_data(
        db,
        TrainingDataAuditConfig(
            min_replay_days=1,
            min_replay_samples=1,
            max_replay_avg_per_day=3,
            require_replay_validation=False,
        ),
    )

    assert result["ok"] is False
    assert "required_feature_missing" in result["errors"]
    assert "non_a_share_sample_detected" in result["errors"]
    assert "replay_avg_count_above_threshold" in result["errors"]
    assert result["feature_missing_counts"]["seal_rate"] == 1
    assert result["code_quality"]["non_a_share_codes"] == ["HK0001.HK"]


def test_training_data_audit_reports_cross_source_duplicate_date_code(db):
    _clear_training_samples(db)
    db.add_all(
        [
            _sample("20260506", "000001.SZ", sample_source="replay_backtest"),
            _sample("20260506", "000001.SZ", sample_source="real_selected"),
        ]
    )
    db.commit()

    result = audit_default_auction_training_data(
        db,
        TrainingDataAuditConfig(
            min_replay_days=1,
            min_replay_samples=1,
            require_replay_validation=False,
        ),
    )

    assert result["ok"] is True
    assert "cross_source_duplicate_date_code" in result["warnings"]
    assert result["cross_source_duplicate_keys"] == [
        {
            "strategy_version": "default_auction_v2",
            "trade_date": "20260506",
            "ts_code": "000001.SZ",
            "sample_sources": ["real_selected", "replay_backtest"],
            "count": 2,
        }
    ]
