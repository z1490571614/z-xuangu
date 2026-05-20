import json

from backend.database import Base, engine
from backend.models import DefaultAuctionTrainingSample, ModelVersion
from backend.services.model_engine import default_auction_backtest_service


def _clear_tables(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(ModelVersion).delete()
    db.commit()


def _add_sample(db, trade_date, ts_code, auction_ratio, labels):
    db.add(
        DefaultAuctionTrainingSample(
            trade_date=trade_date,
            ts_code=ts_code,
            name=ts_code,
            strategy_name="default",
            strategy_version="default_auction_v2",
            sample_source="replay_backtest",
            replay_source="local_replay",
            auction_source="stock_auction_open",
            auction_ratio_unit="percent",
            auction_turnover_rate_basis="free_float",
            feature_json=json.dumps(
                {"auction_ratio": auction_ratio, "auction_turnover_rate": auction_ratio / 10},
                ensure_ascii=False,
            ),
            **labels,
        )
    )


def _add_model(db, model_name):
    db.add(
        ModelVersion(
            model_name=model_name,
            version=f"{model_name}_v1",
            feature_cols=json.dumps(["auction_ratio", "auction_turnover_rate"], ensure_ascii=False),
            params=json.dumps({"feature_units": {"auction_ratio": "percent"}}, ensure_ascii=False),
            model_path=f"/tmp/{model_name}.pkl",
            is_active=1,
        )
    )


def test_run_default_auction_target_backtest_uses_samples_and_active_model(db, monkeypatch):
    _clear_tables(db)
    model_name = "default_auction_t0_limit_lgbm"
    _add_model(db, model_name)
    for trade_date in ["20260501", "20260502"]:
        _add_sample(db, trade_date, f"{trade_date}A.SZ", 9, {"label_t0_limit_success": 1})
        _add_sample(db, trade_date, f"{trade_date}B.SZ", 7, {"label_t0_limit_success": 0})
        _add_sample(db, trade_date, f"{trade_date}C.SZ", 5, {"label_t0_limit_success": 0})
    db.commit()

    monkeypatch.setattr(
        default_auction_backtest_service.lightgbm_service,
        "_predict_with_model_path",
        lambda model_name, path, cols, features, units: features["auction_ratio"],
    )

    result = default_auction_backtest_service.run_default_auction_target_backtest(
        db,
        model_name=model_name,
        label_column="label_t0_limit_success",
        start_date="20260501",
        end_date="20260502",
    )

    assert result["model_name"] == model_name
    assert result["version"] == f"{model_name}_v1"
    assert result["label_column"] == "label_t0_limit_success"
    assert result["prediction_failed_count"] == 0
    assert result["metrics"]["sample_count"] == 6
    assert result["metrics"]["baseline_rate"] == 0.3333
    assert result["metrics"]["top1_rate"] == 1.0
    assert result["metrics"]["top1_lift"] == 0.6667


def test_run_default_auction_relay_backtest_returns_three_targets(db, monkeypatch):
    _clear_tables(db)
    for model_name in default_auction_backtest_service.TARGET_LABELS:
        _add_model(db, model_name)
    _add_sample(
        db,
        "20260501",
        "000001.SZ",
        9,
        {
            "label_t0_limit_success": 1,
            "label_t1_premium_success": 1,
            "label_t1_continue_limit": 0,
        },
    )
    db.commit()
    monkeypatch.setattr(
        default_auction_backtest_service.lightgbm_service,
        "_predict_with_model_path",
        lambda model_name, path, cols, features, units: features["auction_ratio"],
    )

    result = default_auction_backtest_service.run_default_auction_relay_backtest(
        db,
        start_date="20260501",
        end_date="20260501",
    )

    assert set(result["targets"]) == set(default_auction_backtest_service.TARGET_LABELS)
    assert result["targets"]["default_auction_t1_continue_lgbm"]["metrics"]["baseline_rate"] == 0.0


def test_run_default_auction_relay_backtest_accepts_target_version_mapping(db, monkeypatch):
    _clear_tables(db)
    for model_name in default_auction_backtest_service.TARGET_LABELS:
        _add_model(db, model_name)
        db.add(
            ModelVersion(
                model_name=model_name,
                version=f"{model_name}_new",
                feature_cols=json.dumps(["auction_ratio", "auction_turnover_rate"], ensure_ascii=False),
                params=json.dumps({"feature_units": {"auction_ratio": "percent"}}, ensure_ascii=False),
                model_path=f"/tmp/{model_name}_new.pkl",
                is_active=0,
            )
        )
    _add_sample(
        db,
        "20260501",
        "000001.SZ",
        9,
        {
            "label_t0_limit_success": 1,
            "label_t1_premium_success": 1,
            "label_t1_continue_limit": 0,
        },
    )
    db.commit()
    monkeypatch.setattr(
        default_auction_backtest_service.lightgbm_service,
        "_predict_with_model_path",
        lambda model_name, path, cols, features, units: features["auction_ratio"],
    )

    result = default_auction_backtest_service.run_default_auction_relay_backtest(
        db,
        start_date="20260501",
        end_date="20260501",
        target_versions={
            model_name: f"{model_name}_new"
            for model_name in default_auction_backtest_service.TARGET_LABELS
        },
    )

    for model_name in default_auction_backtest_service.TARGET_LABELS:
        assert result["targets"][model_name]["version"] == f"{model_name}_new"
